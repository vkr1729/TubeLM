/**
 * TubeLM Cross-Device State Synchronization & Audio CDN Worker
 * 
 * 1. Synchronizes watch history and channel read states across devices
 *    using signed timestamp LWW-Element-Set CRDT (supports both mark read and unmarking/unwatching).
 * 2. Directly streams audio digests from the TubeLM R2 bucket with HTTP Range request support.
 * 
 * Zero external dependencies. Uses standard Web Crypto API.
 */

async function sha256(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Sync-Key, Range',
  'Access-Control-Expose-Headers': 'Content-Range, Accept-Ranges, Content-Length, Content-Type',
  'Access-Control-Max-Age': '86400',
};

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...CORS_HEADERS,
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store, no-cache, must-revalidate',
    },
  });
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(request.url);

    // ── AUDIO CDN: Stream podcast digests directly from R2 ────────────────
    if (url.pathname.startsWith('/tubelm/audio/')) {
      if (!env.SYNC_BUCKET) {
        return new Response('R2 bucket binding (SYNC_BUCKET) not configured', { status: 500 });
      }
      const objKey = url.pathname.replace(/^\/+/, '');
      const hasRange = request.headers.has('range');
      const getOpts = hasRange ? { range: request.headers, onlyIf: request.headers } : { onlyIf: request.headers };
      try {
        const obj = await env.SYNC_BUCKET.get(objKey, getOpts);
        if (!obj) {
          return new Response('Audio file not found in bucket', { status: 404 });
        }
        const headers = new Headers();
        obj.writeHttpMetadata(headers);
        headers.set('etag', obj.httpEtag);
        headers.set('Cache-Control', 'public, max-age=31536000, immutable');
        headers.set('Access-Control-Allow-Origin', '*');
        headers.set('Accept-Ranges', 'bytes');
        if (!headers.has('Content-Type')) {
          headers.set('Content-Type', 'audio/mpeg');
        }
        return new Response(obj.body, {
          headers,
          status: obj.range ? 206 : 200,
        });
      } catch (err) {
        return new Response('Failed to read audio: ' + err.message, { status: 500 });
      }
    }

    // ── STATE SYNC AUTH: Verify secret sync passphrase ────────────────────
    const authHeader = request.headers.get('Authorization') || '';
    const syncKeyHeader = request.headers.get('X-Sync-Key') || '';
    const rawKey =
      url.searchParams.get('key') ||
      syncKeyHeader ||
      authHeader.replace(/^Bearer\s+/i, '').trim();

    if (!rawKey || rawKey.length < 4) {
      return jsonResponse({ error: 'Missing or invalid sync key (minimum 4 characters required)' }, 401);
    }

    // Hash sync key to prevent directory traversal and provide an isolated object key in R2
    const hashedKey = await sha256(rawKey);
    const objectPath = 'sync/' + hashedKey + '.json';

    // ── GET: Retrieve state ───────────────────────────────────────────────
    if (request.method === 'GET') {
      try {
        if (!env.SYNC_BUCKET) {
          return jsonResponse({ error: 'R2 bucket binding (SYNC_BUCKET) not configured in wrangler.toml' }, 500);
        }

        const obj = await env.SYNC_BUCKET.get(objectPath);
        if (!obj) {
          return jsonResponse({
            read_ids: [],
            top20_read: [],
            item_states: {},
            updated_at: null,
            message: 'No remote state yet for this key',
          });
        }

        const data = await obj.json();
        return jsonResponse({
          read_ids: Array.isArray(data.read_ids) ? data.read_ids : [],
          top20_read: Array.isArray(data.top20_read) ? data.top20_read : [],
          item_states: (data.item_states && typeof data.item_states === 'object') ? data.item_states : {},
          updated_at: data.updated_at || null,
        });
      } catch (err) {
        return jsonResponse({ error: 'Failed to read from storage: ' + err.message }, 500);
      }
    }

    // ── POST: Push & Merge state (LWW-Element-Set CRDT) ───────────────────
    if (request.method === 'POST') {
      try {
        if (!env.SYNC_BUCKET) {
          return jsonResponse({ error: 'R2 bucket binding (SYNC_BUCKET) not configured in wrangler.toml' }, 500);
        }

        const payload = await request.json().catch(() => ({}));
        const incomingStates = (payload.item_states && typeof payload.item_states === 'object') ? payload.item_states : {};
        const incomingReadIds = Array.isArray(payload.read_ids) ? payload.read_ids : [];
        const incomingTop20 = Array.isArray(payload.top20_read) ? payload.top20_read : [];

        // Fetch existing state
        let existingStates = {};
        const existingObj = await env.SYNC_BUCKET.get(objectPath);
        if (existingObj) {
          try {
            const existingData = await existingObj.json();
            if (existingData.item_states && typeof existingData.item_states === 'object') {
              existingStates = existingData.item_states;
            } else {
              // Backward compatibility for existing data without item_states
              const baseTs = existingData.updated_at ? new Date(existingData.updated_at).getTime() : (Date.now() - 3600000);
              (existingData.read_ids || []).forEach(id => { existingStates[id] = baseTs; });
              (existingData.top20_read || []).forEach(id => { existingStates[id] = baseTs; });
            }
          } catch (_) {}
        }

        // Merge item states based on largest absolute timestamp (most recent intent wins)
        const mergedStates = { ...existingStates };

        // Process explicit incoming signed timestamps:
        // positive ts (> 0) means marked WATCHED/READ
        // negative ts (< 0) means marked UNWATCHED/UNREAD
        for (const [key, ts] of Object.entries(incomingStates)) {
          if (typeof ts === 'number') {
            const cur = mergedStates[key] || 0;
            if (Math.abs(ts) >= Math.abs(cur)) {
              mergedStates[key] = ts;
            }
          }
        }

        // Incorporate incoming arrays if any items were not in item_states
        const nowTs = Date.now();
        incomingReadIds.forEach(id => {
          if (mergedStates[id] === undefined) mergedStates[id] = nowTs;
        });
        incomingTop20.forEach(id => {
          if (mergedStates[id] === undefined) mergedStates[id] = nowTs;
        });

        // Preserve category partition (read_ids vs top20_read), filtering out unread (ts < 0) items
        let existingReadIds = [];
        let existingTop20 = [];
        if (existingObj) {
          try {
            const existingData = await existingObj.json();
            if (Array.isArray(existingData.read_ids)) existingReadIds = existingData.read_ids;
            if (Array.isArray(existingData.top20_read)) existingTop20 = existingData.top20_read;
          } catch (_) {}
        }

        const mergedReadIds = Array.from(new Set([...existingReadIds, ...incomingReadIds]))
          .filter(id => (mergedStates[id] === undefined || mergedStates[id] > 0))
          .slice(0, 5000);

        const mergedTop20 = Array.from(new Set([...existingTop20, ...incomingTop20]))
          .filter(id => (mergedStates[id] === undefined || mergedStates[id] > 0))
          .slice(0, 5000);

        const nowIso = new Date().toISOString();

        const mergedState = {
          read_ids: mergedReadIds,
          top20_read: mergedTop20,
          item_states: mergedStates,
          updated_at: nowIso,
        };

        await env.SYNC_BUCKET.put(objectPath, JSON.stringify(mergedState), {
          httpMetadata: { contentType: 'application/json' },
        });

        return jsonResponse({
          ok: true,
          read_ids: mergedReadIds,
          top20_read: mergedTop20,
          item_states: mergedStates,
          updated_at: nowIso,
        });
      } catch (err) {
        return jsonResponse({ error: 'Failed to save state: ' + err.message }, 500);
      }
    }

    return jsonResponse({ error: 'Method not allowed' }, 405);
  },
};
