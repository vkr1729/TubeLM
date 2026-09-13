/**
 * TubeLM Cross-Device State Synchronization Worker
 * 
 * Securely synchronizes watch history and channel read state across devices
 * (laptops, phones, tablets) backed by Cloudflare R2.
 * 
 * Zero external dependencies. Uses standard Web Crypto API for isolated SHA-256 key hashing.
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
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Sync-Key',
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

    // Extract secret sync key from Header or Query Param
    const authHeader = request.headers.get('Authorization') || '';
    const syncKeyHeader = request.headers.get('X-Sync-Key') || '';
    const rawKey =
      url.searchParams.get('key') ||
      syncKeyHeader ||
      authHeader.replace(/^Bearer\s+/i, '').trim();

    if (!rawKey || rawKey.length < 4) {
      return jsonResponse({ error: 'Missing or invalid sync key (minimum 4 characters required)' }, 401);
    }

    // Hash sync key to prevent directory traversal and provide a deterministic, isolated object key
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
            updated_at: null,
            message: 'No remote state yet for this key',
          });
        }

        const data = await obj.json();
        return jsonResponse({
          read_ids: Array.isArray(data.read_ids) ? data.read_ids : [],
          top20_read: Array.isArray(data.top20_read) ? data.top20_read : [],
          updated_at: data.updated_at || null,
        });
      } catch (err) {
        return jsonResponse({ error: 'Failed to read from storage: ' + err.message }, 500);
      }
    }

    // ── POST: Push & Merge state ──────────────────────────────────────────
    if (request.method === 'POST') {
      try {
        if (!env.SYNC_BUCKET) {
          return jsonResponse({ error: 'R2 bucket binding (SYNC_BUCKET) not configured in wrangler.toml' }, 500);
        }

        const payload = await request.json().catch(() => ({}));
        const incomingReadIds = Array.isArray(payload.read_ids) ? payload.read_ids : [];
        const incomingTop20 = Array.isArray(payload.top20_read) ? payload.top20_read : [];

        // Fetch existing state for robust additive CRDT set-union
        let existingReadIds = [];
        let existingTop20 = [];
        const existingObj = await env.SYNC_BUCKET.get(objectPath);
        if (existingObj) {
          try {
            const existingData = await existingObj.json();
            if (Array.isArray(existingData.read_ids)) existingReadIds = existingData.read_ids;
            if (Array.isArray(existingData.top20_read)) existingTop20 = existingData.top20_read;
          } catch (_) {}
        }

        // Additive union: neither device ever wipes out the other device watch history
        const mergedReadIds = Array.from(new Set([...existingReadIds, ...incomingReadIds])).slice(0, 5000);
        const mergedTop20 = Array.from(new Set([...existingTop20, ...incomingTop20])).slice(0, 5000);
        const nowIso = new Date().toISOString();

        const mergedState = {
          read_ids: mergedReadIds,
          top20_read: mergedTop20,
          updated_at: nowIso,
        };

        await env.SYNC_BUCKET.put(objectPath, JSON.stringify(mergedState), {
          httpMetadata: { contentType: 'application/json' },
        });

        return jsonResponse({
          ok: true,
          read_ids: mergedReadIds,
          top20_read: mergedTop20,
          updated_at: nowIso,
        });
      } catch (err) {
        return jsonResponse({ error: 'Failed to save state: ' + err.message }, 500);
      }
    }

    return jsonResponse({ error: 'Method not allowed' }, 405);
  },
};
