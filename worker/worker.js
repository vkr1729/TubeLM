/**
 * TubeLM Cross-Device State Synchronization & Audio CDN Worker
 *
 * 1. Synchronizes watch history and channel read states across devices
 *    using signed timestamp LWW-Element-Set CRDT (supports both mark read and unmarking/unwatching).
 * 2. Directly streams audio digests from the TubeLM R2 bucket with HTTP Range request support.
 *
 * Zero external dependencies. Uses standard Web Crypto API.
 *
 * Security model:
 * - Sync auth is a user-chosen passphrase (min 16 chars) sent ONLY in the
 *   Authorization / X-Sync-Key headers. It is hashed to derive the R2 object
 *   name, so key knowledge equals read+write access to that namespace.
 * - Front-end rate limiting is per-isolate best-effort; per-key limiting inside
 *   the Durable Object is exact. Enumeration of a 16+ char passphrase online is
 *   infeasible under these limits, but treat the passphrase as a credential:
 *   never share it and rotate (pick a new one) if it ever leaks.
 */

// ── Tunables ────────────────────────────────────────────────────────────────
const MIN_KEY_LENGTH = 16;
const MAX_KEY_LENGTH = 256;
const MAX_PAYLOAD_BYTES = 1024 * 1024; // 1 MiB per sync push
const MAX_ITEM_STATES = 5000;
const MAX_ARRAY_IDS = 5000;
const MAX_ID_LENGTH = 256;
const MAX_BOOKMARKS = 1000;
const MAX_BOOKMARK_STATES = 5000;
const RATE_LIMIT_MAX = 60; // requests per window per client IP (best-effort)
const RATE_LIMIT_WINDOW_MS = 60 * 1000;
const DO_RATE_LIMIT_MAX = 240; // pushes per window per sync key (exact, in-DO)
const CONTROL_CHARS_RE = /[\x00-\x1f\x7f]/;

// Reader origins allowed to call the sync API from a browser.
const ALLOWED_ORIGIN_HOSTS = new Set(['vkr1729.github.io']);
const ALLOWED_DEV_HOSTS = new Set(['localhost', '127.0.0.1']);

async function sha256(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function isAllowedOrigin(origin, env) {
  if (!origin) return false;
  try {
    const url = new URL(origin);
    if (ALLOWED_ORIGIN_HOSTS.has(url.hostname) && url.protocol === 'https:') return true;
    if (ALLOWED_DEV_HOSTS.has(url.hostname) && url.protocol === 'http:') return true;
    const extra = (env && env.ALLOWED_ORIGINS) || '';
    for (const entry of extra.split(',')) {
      if (entry.trim() && entry.trim() === url.origin) return true;
    }
  } catch (_) {
    return false;
  }
  return false;
}

function syncCorsHeaders(origin, env) {
  const headers = {
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Sync-Key, Range',
    'Access-Control-Max-Age': '86400',
  };
  if (origin && isAllowedOrigin(origin, env)) {
    headers['Access-Control-Allow-Origin'] = new URL(origin).origin;
    headers['Vary'] = 'Origin';
  }
  return headers;
}

function jsonResponse(data, status = 200, origin = null, env = null) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...syncCorsHeaders(origin, env),
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store, no-cache, must-revalidate',
    },
  });
}

function utf8Length(text) {
  // text.length counts UTF-16 code units and undercounts multibyte bodies;
  // the cap is in bytes, matching the Content-Length pre-check.
  return new TextEncoder().encode(text).length;
}

function serverError(origin, env, err, context) {
  // Log internals server-side; callers get a generic message + correlation id.
  const correlationId = (crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
  try {
    console.error(`[tubelm-sync:${correlationId}] ${context}:`, err);
  } catch (_) {}
  return jsonResponse({ error: 'Internal sync error', correlationId }, 500, origin, env);
}

// ── Best-effort per-isolate rate limiting ────────────────────────────────────
// NOTE: each isolate keeps its own buckets, so this is approximate under load.
// It still defeats casual enumeration; exact per-key limiting lives in the DO.
const _rateBuckets = new Map();

function isRateLimited(clientId) {
  const now = Date.now();
  let bucket = _rateBuckets.get(clientId);
  if (!bucket || now - bucket.start >= RATE_LIMIT_WINDOW_MS) {
    bucket = { start: now, count: 0 };
    _rateBuckets.set(clientId, bucket);
  }
  bucket.count += 1;
  if (_rateBuckets.size > 10000) {
    for (const [key, entry] of _rateBuckets) {
      if (now - entry.start >= RATE_LIMIT_WINDOW_MS) _rateBuckets.delete(key);
      if (_rateBuckets.size <= 5000) break;
    }
    // An in-window IP flood defeats expiry-only cleanup: evict oldest first.
    // (Map iterates in insertion order, so shift from the front.)
    while (_rateBuckets.size > 10000) {
      _rateBuckets.delete(_rateBuckets.keys().next().value);
    }
  }
  return bucket.count > RATE_LIMIT_MAX;
}

function clientIp(request) {
  // CF-Connecting-IP is set by Cloudflare and cannot be spoofed by clients.
  // X-Forwarded-For is deliberately NOT consulted: it is attacker-controlled
  // and would let one client rotate through unlimited buckets.
  const direct = request.headers.get('CF-Connecting-IP');
  if (direct && direct.trim()) return direct.trim();
  return 'unknown';
}

function extractSyncKey(request) {
  // Headers only: a ?key= query would leak the credential into logs/history.
  const authHeader = request.headers.get('Authorization') || '';
  const syncKeyHeader = request.headers.get('X-Sync-Key') || '';
  const bearer = authHeader.replace(/^Bearer\s+/i, '').trim();
  const key = (syncKeyHeader || bearer).trim();
  if (!key) return { error: 'Missing sync key (send Authorization: Bearer or X-Sync-Key)' };
  if (key.length < MIN_KEY_LENGTH) {
    return { error: `Invalid sync key (minimum ${MIN_KEY_LENGTH} characters required)` };
  }
  if (key.length > MAX_KEY_LENGTH || CONTROL_CHARS_RE.test(key)) {
    return { error: 'Invalid sync key' };
  }
  return { key };
}

// ── Payload validation ──────────────────────────────────────────────────────
function sanitizeIdArray(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  const clean = [];
  for (const id of value) {
    if (typeof id !== 'string' || !id || id.length > MAX_ID_LENGTH) continue;
    if (CONTROL_CHARS_RE.test(id)) continue;
    if (seen.has(id)) continue;
    seen.add(id);
    clean.push(id);
    if (clean.length >= MAX_ARRAY_IDS) break;
  }
  return clean;
}

function sanitizeItemStates(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const clean = {};
  for (const [key, ts] of Object.entries(value)) {
    if (typeof key !== 'string' || !key || key.length > MAX_ID_LENGTH) continue;
    if (CONTROL_CHARS_RE.test(key)) continue;
    if (typeof ts !== 'number' || !Number.isFinite(ts)) continue;
    clean[key] = ts;
  }
  return capStates(clean, MAX_ITEM_STATES);
}

function capStates(states, limit) {
  const keys = Object.keys(states);
  if (keys.length <= limit) return states;
  // Evict the stalest intent first: keep the largest absolute timestamps.
  keys.sort((a, b) => Math.abs(states[b]) - Math.abs(states[a]));
  const capped = {};
  for (const key of keys.slice(0, limit)) capped[key] = states[key];
  return capped;
}

function sanitizeBookmarkItem(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  if (typeof item.id !== 'string' || !item.id || item.id.length > MAX_ID_LENGTH) return null;
  if (CONTROL_CHARS_RE.test(item.id)) return null;

  const clean = {
    id: item.id,
    title: (typeof item.title === 'string' ? item.title.slice(0, 500) : ''),
    source_name: (typeof item.source_name === 'string' ? item.source_name.slice(0, 256) : ''),
    source_type: (typeof item.source_type === 'string' ? item.source_type.slice(0, 64) : 'youtube'),
  };

  if (typeof item.rank === 'number' && Number.isFinite(item.rank)) {
    clean.rank = Math.floor(item.rank);
  }
  if (typeof item.duration === 'string') {
    clean.duration = item.duration.slice(0, 64);
  }
  if (typeof item.duration_seconds === 'number' && Number.isFinite(item.duration_seconds)) {
    clean.duration_seconds = Math.floor(item.duration_seconds);
  }
  if (typeof item.why_it_matters === 'string') {
    clean.why_it_matters = item.why_it_matters.slice(0, 2000);
  }
  if (typeof item.url === 'string') {
    clean.url = item.url.slice(0, 2048);
  }
  if (typeof item.audio_url === 'string') {
    clean.audio_url = item.audio_url.slice(0, 2048);
  }
  return clean;
}

function sanitizeBookmarksArray(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  const clean = [];
  for (const raw of value) {
    const item = sanitizeBookmarkItem(raw);
    if (!item) continue;
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    clean.push(item);
    if (clean.length >= MAX_BOOKMARKS) break;
  }
  return clean;
}

// ── Shared merge (single-fetch; used by the DO and the direct fallback) ─────
function mergeSyncState(existing, payload, nowMs) {
  const incomingStates = sanitizeItemStates(payload.item_states);
  const incomingReadIds = sanitizeIdArray(payload.read_ids);
  const incomingTop20 = sanitizeIdArray(payload.top20_read);

  let existingStates = {};
  let existingReadIds = [];
  let existingTop20 = [];
  if (existing) {
    if (existing.item_states && typeof existing.item_states === 'object') {
      for (const [key, ts] of Object.entries(existing.item_states)) {
        if (typeof ts === 'number' && Number.isFinite(ts)) existingStates[key] = ts;
      }
    } else {
      // Backward compatibility for data written before item_states existed.
      // Guarded: a corrupt out-of-band shape must heal, not write-brick the key.
      let baseTs = existing.updated_at ? new Date(existing.updated_at).getTime() : (nowMs - 3600000);
      if (!Number.isFinite(baseTs)) baseTs = nowMs - 3600000;
      const legacyReadIds = Array.isArray(existing.read_ids) ? existing.read_ids : [];
      const legacyTop20 = Array.isArray(existing.top20_read) ? existing.top20_read : [];
      legacyReadIds.forEach((id) => { existingStates[id] = baseTs; });
      legacyTop20.forEach((id) => { existingStates[id] = baseTs; });
    }
    existingReadIds = sanitizeIdArray(existing.read_ids);
    existingTop20 = sanitizeIdArray(existing.top20_read);
  }

  // Merge on largest absolute timestamp (most recent intent wins).
  // Positive ts (> 0) = marked READ; negative ts (< 0) = marked UNREAD.
  const mergedStates = { ...existingStates };
  for (const [key, ts] of Object.entries(incomingStates)) {
    const cur = mergedStates[key] || 0;
    if (Math.abs(ts) >= Math.abs(cur)) {
      mergedStates[key] = ts;
    }
  }

  // Incorporate incoming arrays for items missing from item_states.
  incomingReadIds.forEach((id) => {
    if (mergedStates[id] === undefined) mergedStates[id] = nowMs;
  });
  incomingTop20.forEach((id) => {
    if (mergedStates[id] === undefined) mergedStates[id] = nowMs;
  });

  // Preserve category partition, filtering out unread (ts < 0) items.
  const mergedReadIds = Array.from(new Set([...existingReadIds, ...incomingReadIds]))
    .filter((id) => (mergedStates[id] === undefined || mergedStates[id] > 0))
    .slice(0, MAX_ARRAY_IDS);

  const mergedTop20 = Array.from(new Set([...existingTop20, ...incomingTop20]))
    .filter((id) => (mergedStates[id] === undefined || mergedStates[id] > 0))
    .slice(0, MAX_ARRAY_IDS);

  // ── Bookmarks CRDT Merge (LWW signed timestamps & tombstones) ───────────────
  const hasIncomingBookmarkStates = payload.bookmark_states && typeof payload.bookmark_states === 'object' && !Array.isArray(payload.bookmark_states);
  const hasIncomingBookmarks = Array.isArray(payload.bookmarks);

  const incomingBookmarkStates = hasIncomingBookmarkStates ? sanitizeItemStates(payload.bookmark_states) : {};
  const incomingBookmarks = hasIncomingBookmarks ? sanitizeBookmarksArray(payload.bookmarks) : [];

  let existingBookmarkStates = {};
  let existingBookmarks = [];
  if (existing) {
    if (existing.bookmark_states && typeof existing.bookmark_states === 'object') {
      for (const [key, ts] of Object.entries(existing.bookmark_states)) {
        if (typeof ts === 'number' && Number.isFinite(ts)) existingBookmarkStates[key] = ts;
      }
    }
    existingBookmarks = sanitizeBookmarksArray(existing.bookmarks);
  }

  const mergedBookmarkStates = { ...existingBookmarkStates };
  for (const [key, ts] of Object.entries(incomingBookmarkStates)) {
    const cur = mergedBookmarkStates[key] || 0;
    if (Math.abs(ts) >= Math.abs(cur)) {
      mergedBookmarkStates[key] = ts;
    }
  }

  incomingBookmarks.forEach((item) => {
    if (mergedBookmarkStates[item.id] === undefined) mergedBookmarkStates[item.id] = nowMs;
  });
  existingBookmarks.forEach((item) => {
    if (mergedBookmarkStates[item.id] === undefined) mergedBookmarkStates[item.id] = nowMs;
  });

  const itemsMap = new Map();
  for (const item of existingBookmarks) {
    itemsMap.set(item.id, item);
  }
  for (const item of incomingBookmarks) {
    itemsMap.set(item.id, item);
  }

  const mergedBookmarks = [];
  for (const [id, item] of itemsMap.entries()) {
    const ts = mergedBookmarkStates[id];
    if (ts !== undefined && ts > 0) {
      mergedBookmarks.push(item);
    }
  }

  mergedBookmarks.sort((a, b) => (mergedBookmarkStates[b.id] || 0) - (mergedBookmarkStates[a.id] || 0));
  const cappedBookmarks = mergedBookmarks.slice(0, MAX_BOOKMARKS);

  return {
    read_ids: mergedReadIds,
    top20_read: mergedTop20,
    item_states: capStates(mergedStates, MAX_ITEM_STATES),
    bookmarks: cappedBookmarks,
    bookmark_states: capStates(mergedBookmarkStates, MAX_BOOKMARK_STATES),
    updated_at: new Date(nowMs).toISOString(),
  };
}

async function readStoredState(bucket, objectPath) {
  // Single fetch + single parse: R2 bodies are single-use streams.
  const obj = await bucket.get(objectPath);
  if (!obj) return null;
  try {
    return await obj.json();
  } catch (_) {
    return null;
  }
}

// ── Durable Object: serializes read-modify-write per sync key ────────────────
export class SyncCoordinator {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.pushes = { start: 0, count: 0 };
  }

  async fetch(request) {
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Method not allowed' }), {
        status: 405,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    const objectPath = request.headers.get('X-Sync-Object') || '';
    if (!/^sync\/[0-9a-f]{64}\.json$/.test(objectPath)) {
      return new Response(JSON.stringify({ error: 'Bad sync object' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    // Exact per-key rate limit (one instance owns each key).
    const now = Date.now();
    if (now - this.pushes.start >= RATE_LIMIT_WINDOW_MS) {
      this.pushes = { start: now, count: 0 };
    }
    this.pushes.count += 1;
    if (this.pushes.count > DO_RATE_LIMIT_MAX) {
      return new Response(JSON.stringify({ error: 'Rate limited, retry shortly' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
      });
    }
    try {
      if (!this.env.SYNC_BUCKET) {
        return new Response(JSON.stringify({ error: 'Storage binding not configured' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      const text = await request.text();
      if (utf8Length(text) > MAX_PAYLOAD_BYTES) {
        return new Response(JSON.stringify({ error: 'Sync payload too large' }), {
          status: 413,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      let payload;
      try {
        payload = JSON.parse(text || '{}');
      } catch (_) {
        return new Response(JSON.stringify({ error: 'Malformed sync payload' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      // Atomic within this DO: concurrent pushes for the same key queue here.
      const existing = await readStoredState(this.env.SYNC_BUCKET, objectPath);
      const merged = mergeSyncState(existing, payload || {}, Date.now());
      await this.env.SYNC_BUCKET.put(objectPath, JSON.stringify(merged), {
        httpMetadata: { contentType: 'application/json' },
      });
      return new Response(JSON.stringify({ ok: true, ...merged }), {
        headers: { 'Content-Type': 'application/json' },
      });
    } catch (err) {
      try {
        console.error('[tubelm-sync:do] merge failed:', err);
      } catch (_) {}
      return new Response(JSON.stringify({ error: 'Failed to save state' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  }
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin');
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      if (!url.pathname.startsWith('/tubelm/audio/') && origin && !isAllowedOrigin(origin, env)) {
        return jsonResponse({ error: 'Origin not allowed' }, 403, origin, env);
      }
      if (url.pathname.startsWith('/tubelm/audio/')) {
        // Full preflight set: cross-origin fetch() with Range must pass CORS.
        return new Response(null, {
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Range',
            'Access-Control-Max-Age': '86400',
          },
        });
      }
      return new Response(null, { headers: syncCorsHeaders(origin, env) });
    }

    // ── AUDIO CDN: Stream podcast digests directly from R2 ────────────────
    if (url.pathname.startsWith('/tubelm/audio/')) {
      if (!env.SYNC_BUCKET) {
        return new Response('R2 bucket binding (SYNC_BUCKET) not configured', { status: 500 });
      }
      const objKey = url.pathname.replace(/^\/+/, '');
      const rangeHeader = request.headers.get('range');
      const hasRange = Boolean(rangeHeader && rangeHeader.trim());
      const getOpts = hasRange ? { range: request.headers, onlyIf: request.headers } : { onlyIf: request.headers };
      try {
        const obj = await env.SYNC_BUCKET.get(objKey, getOpts);
        if (!obj) {
          return new Response('Audio file not found in bucket', { status: 404 });
        }
        const headers = new Headers();
        obj.writeHttpMetadata(headers);
        if (obj.httpEtag) headers.set('etag', obj.httpEtag);
        headers.set('Cache-Control', 'public, max-age=31536000, immutable');
        headers.set('Access-Control-Allow-Origin', '*');
        headers.set('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
        headers.set('Access-Control-Allow-Headers', 'Range, Content-Type');
        headers.set('Access-Control-Expose-Headers', 'Content-Range, Accept-Ranges, Content-Length, Content-Type, ETag');
        headers.set('Accept-Ranges', 'bytes');
        if (!headers.has('Content-Type')) {
          headers.set('Content-Type', 'audio/mpeg');
        }

        const isHead = request.method === 'HEAD';
        const body = isHead ? null : obj.body;

        if (hasRange && obj.range) {
          const start = obj.range.offset;
          const end = obj.range.offset + obj.range.length - 1;
          const total = obj.size;
          headers.set('Content-Range', `bytes ${start}-${end}/${total}`);
          headers.set('Content-Length', String(obj.range.length));
          return new Response(body, {
            headers,
            status: 206,
          });
        }

        headers.set('Content-Length', String(obj.size));
        return new Response(body, {
          headers,
          status: 200,
        });
      } catch (err) {
        try {
          console.error('[tubelm-sync] audio read failed:', err);
        } catch (_) {}
        return new Response('Failed to read audio', { status: 500 });
      }
    }

    // ── STATE SYNC AUTH ───────────────────────────────────────────────────
    if (isRateLimited(clientIp(request))) {
      const res = jsonResponse({ error: 'Rate limited, retry shortly' }, 429, origin, env);
      res.headers.set('Retry-After', '60');
      return res;
    }

    const auth = extractSyncKey(request);
    if (auth.error) {
      return jsonResponse({ error: auth.error }, 401, origin, env);
    }

    // Hash sync key to provide an isolated object key in R2.
    const hashedKey = await sha256(auth.key);
    const objectPath = 'sync/' + hashedKey + '.json';

    // ── GET: Retrieve state (reads cannot race; served straight from R2) ──
    if (request.method === 'GET') {
      try {
        if (!env.SYNC_BUCKET) {
          return jsonResponse({ error: 'Storage binding not configured' }, 500, origin, env);
        }
        const data = await readStoredState(env.SYNC_BUCKET, objectPath);
        if (!data) {
          return jsonResponse({
            read_ids: [],
            top20_read: [],
            item_states: {},
            bookmarks: [],
            bookmark_states: {},
            updated_at: null,
            message: 'No remote state yet for this key',
          }, 200, origin, env);
        }
        return jsonResponse({
          read_ids: Array.isArray(data.read_ids) ? data.read_ids : [],
          top20_read: Array.isArray(data.top20_read) ? data.top20_read : [],
          item_states: (data.item_states && typeof data.item_states === 'object') ? data.item_states : {},
          bookmarks: Array.isArray(data.bookmarks) ? sanitizeBookmarksArray(data.bookmarks) : [],
          bookmark_states: (data.bookmark_states && typeof data.bookmark_states === 'object') ? data.bookmark_states : {},
          updated_at: data.updated_at || null,
        }, 200, origin, env);
      } catch (err) {
        return serverError(origin, env, err, 'sync GET');
      }
    }

    // ── POST: Push & Merge state (serialized per key via Durable Object) ──
    if (request.method === 'POST') {
      const contentLength = parseInt(request.headers.get('Content-Length') || '', 10);
      if (Number.isFinite(contentLength) && contentLength > MAX_PAYLOAD_BYTES) {
        return jsonResponse({ error: 'Sync payload too large' }, 413, origin, env);
      }
      if (env.SYNC_COORDINATOR) {
        try {
          const stubId = env.SYNC_COORDINATOR.idFromName('sync-' + hashedKey);
          const stub = env.SYNC_COORDINATOR.get(stubId);
          const bodyText = await request.text();
          if (utf8Length(bodyText) > MAX_PAYLOAD_BYTES) {
            return jsonResponse({ error: 'Sync payload too large' }, 413, origin, env);
          }
          const doRes = await stub.fetch(new Request('https://sync-coordinator/merge', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Sync-Object': objectPath,
            },
            body: bodyText,
          }));
          const data = await doRes.json().catch(() => ({}));
          const relayed = jsonResponse(data, doRes.status, origin, env);
          if (doRes.status === 429) {
            relayed.headers.set('Retry-After', doRes.headers.get('Retry-After') || '60');
          }
          return relayed;
        } catch (err) {
          return serverError(origin, env, err, 'sync POST via coordinator');
        }
      }
      // Fallback for environments without the DO binding (tests, old deploys):
      // correct merge math, but concurrent pushes can still interleave.
      try {
        if (!env.SYNC_BUCKET) {
          return jsonResponse({ error: 'Storage binding not configured' }, 500, origin, env);
        }
        const bodyText = await request.text();
        if (utf8Length(bodyText) > MAX_PAYLOAD_BYTES) {
          return jsonResponse({ error: 'Sync payload too large' }, 413, origin, env);
        }
        let payload;
        try {
          payload = JSON.parse(bodyText || '{}');
        } catch (_) {
          return jsonResponse({ error: 'Malformed sync payload' }, 400, origin, env);
        }
        const existing = await readStoredState(env.SYNC_BUCKET, objectPath);
        const merged = mergeSyncState(existing, payload || {}, Date.now());
        await env.SYNC_BUCKET.put(objectPath, JSON.stringify(merged), {
          httpMetadata: { contentType: 'application/json' },
        });
        return jsonResponse({ ok: true, ...merged }, 200, origin, env);
      } catch (err) {
        return serverError(origin, env, err, 'sync POST direct');
      }
    }

    return jsonResponse({ error: 'Method not allowed' }, 405, origin, env);
  },
};
