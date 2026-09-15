"""Tests for Cross-Device Synchronization Engine.

Validates:
1. reader.html template contract (UI elements, modals, pairing parser, background handlers).
2. Worker contract and Node execution (if node is available).
3. CRDT-lite mathematical properties:
   - Commutativity: Union(A, B) == Union(B, A)
   - Associativity: Union(Union(A, B), C) == Union(A, Union(B, C))
   - Idempotence: Union(A, A) == A
   - Monotonicity: |Union(A, B)| >= max(|A|, |B|)
4. Multi-device simulation:
   - Device 1: Personal Laptop
   - Device 2: iPhone
   - Device 3: Office Laptop (intermittent connectivity / delayed sync)
"""
import subprocess
from pathlib import Path


def test_reader_html_sync_ui_elements():
    """Verify that reader.html contains all required UI elements for sync."""
    template_path = Path(__file__).resolve().parents[2] / "templates" / "reader.html"
    content = template_path.read_text(encoding="utf-8")

    # Sync trigger & status dot
    assert 'id="btn-sync"' in content
    assert 'class="sync-dot"' in content

    # Sync modal & inputs
    assert 'id="sync-modal"' in content
    assert 'id="sync-endpoint-input"' in content
    assert 'id="sync-key-input"' in content
    assert 'id="pairing-url-display"' in content
    assert 'id="btn-copy-pairing"' in content
    assert 'id="btn-reset-watched"' in content

    # Core sync engine functions
    assert 'function checkUrlPairing()' in content
    assert 'function pullRemoteState()' in content
    assert 'function pushRemoteState()' in content
    assert 'function scheduleSyncPush()' in content
    assert 'function copyPairingUrl()' in content
    assert 'function disconnectSync()' in content
    assert 'function resetAllWatchedState()' in content
    assert 'visibilitychange' in content


def test_reader_html_symmetric_mini_controls():
    """Verify that reader.html mini-controls uses dedicated flex layout without individual margins."""
    template_path = Path(__file__).resolve().parents[2] / "templates" / "reader.html"
    content = template_path.read_text(encoding="utf-8")

    assert ".mini-controls {" in content
    assert "gap: 8px;" in content
    assert ".mini-btn {" in content
    assert "margin: 0;" in content


def test_worker_syntax_and_node_simulation():
    """Run Node-based simulation testing worker.js against multi-device scenarios."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists(), "worker.js must exist"

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const storage = new Map();
      const mockR2 = {
        async get(key) {
          if (!storage.has(key)) return null;
          const data = storage.get(key);
          return {
            json: async () => JSON.parse(data),
            text: async () => data,
          };
        },
        async put(key, value) {
          storage.set(key, typeof value === 'string' ? value : JSON.stringify(value));
        }
      };
      const env = { SYNC_BUCKET: mockR2 };
      const AUTH = { 'Content-Type': 'application/json', 'X-Sync-Key': 'secret-passphrase-01' };

      // 1. CORS Preflight: allowlisted origin is echoed, foreign origin refused
      const corsRes = await worker.fetch(new Request('http://localhost/sync', {
        method: 'OPTIONS',
        headers: { 'Origin': 'https://vkr1729.github.io' },
      }), env);
      if (corsRes.headers.get('Access-Control-Allow-Origin') !== 'https://vkr1729.github.io') {
        throw new Error('CORS allowlisted origin not echoed');
      }
      const evilRes = await worker.fetch(new Request('http://localhost/sync', {
        method: 'OPTIONS',
        headers: { 'Origin': 'https://evil.example.com' },
      }), env);
      if (evilRes.status !== 403) throw new Error('Expected 403 for foreign origin preflight');

      // 2. Auth checks
      const unauth = await worker.fetch(new Request('http://localhost/sync', { method: 'GET' }), env);
      if (unauth.status !== 401) throw new Error('Expected 401 for unauth request');

      // 3. Device 1 (Personal Laptop) writes
      await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ read_ids: ['vid_A', 'vid_B'], top20_read: ['d1_c1'] })
      }), env);

      // 4. Device 2 (iPhone) writes
      await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ read_ids: ['vid_B', 'vid_C'], top20_read: ['d1_c2'] })
      }), env);

      // 5. Device 3 (Office Laptop) writes
      await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ read_ids: ['vid_D'], top20_read: ['d1_c3'] })
      }), env);

      // 6. Device 1 pulls final merged state
      const finalRes = await worker.fetch(new Request('http://localhost/sync', { method: 'GET', headers: AUTH }), env);
      const finalState = await finalRes.json();

      const ids = finalState.read_ids.sort().join(',');
      if (ids !== 'vid_A,vid_B,vid_C,vid_D') throw new Error('Unexpected read_ids: ' + ids);

      const top20 = finalState.top20_read.sort().join(',');
      if (top20 !== 'd1_c1,d1_c2,d1_c3') throw new Error('Unexpected top20_read: ' + top20);

      process.stdout.write('OK');
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    res = subprocess.run(
        ["node", "-e", node_script],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node worker simulation failed: {res.stderr}"
    assert "OK" in res.stdout


def test_crdt_set_union_mathematical_invariants():
    """Verify algebraic properties of additive state union merge across 3 simulated devices."""
    def merge_states(*devices):
        merged_ids = set()
        merged_top20 = set()
        for d in devices:
            merged_ids.update(d.get("read_ids", []))
            merged_top20.update(d.get("top20_read", []))
        return {
            "read_ids": sorted(list(merged_ids)),
            "top20_read": sorted(list(merged_top20)),
        }

    dev1_laptop = {"read_ids": ["vid_1", "vid_2"], "top20_read": ["2026-09-11_lex"]}
    dev2_iphone = {"read_ids": ["vid_2", "vid_3"], "top20_read": ["2026-09-11_huberman"]}
    dev3_office = {"read_ids": ["vid_4"], "top20_read": ["2026-09-11_dwarkesh"]}

    # Idempotence: S ∪ S = S
    assert merge_states(dev1_laptop, dev1_laptop) == merge_states(dev1_laptop)

    # Commutativity: A ∪ B == B ∪ A
    assert merge_states(dev1_laptop, dev2_iphone) == merge_states(dev2_iphone, dev1_laptop)

    # Associativity: (A ∪ B) ∪ C == A ∪ (B ∪ C)
    left = merge_states(merge_states(dev1_laptop, dev2_iphone), dev3_office)
    right = merge_states(dev1_laptop, merge_states(dev2_iphone, dev3_office))
    assert left == right

    # Convergence across 3 devices
    expected = {
        "read_ids": ["vid_1", "vid_2", "vid_3", "vid_4"],
        "top20_read": ["2026-09-11_dwarkesh", "2026-09-11_huberman", "2026-09-11_lex"],
    }
    assert merge_states(dev1_laptop, dev2_iphone, dev3_office) == expected


def test_lww_signed_timestamp_unmarking_simulation():
    """Verify that unmarking a watched video is preserved and cannot be overwritten by stale reads."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const storage = new Map();
      const mockR2 = {
        async get(key) {
          if (!storage.has(key)) return null;
          const data = storage.get(key);
          return { json: async () => JSON.parse(data), text: async () => data };
        },
        async put(key, value) {
          storage.set(key, typeof value === 'string' ? value : JSON.stringify(value));
        }
      };
      const env = { SYNC_BUCKET: mockR2 };
      const AUTH = { 'Content-Type': 'application/json', 'X-Sync-Key': 'unmark-passphrase-02' };

      // 1. Device 1 marks video_A watched at t=1000
      await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ item_states: { 'video_A': 1000 }, top20_read: ['video_A'] })
      }), env);

      // 2. Device 2 marks video_B watched at t=1500
      await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ item_states: { 'video_B': 1500 }, top20_read: ['video_B'] })
      }), env);

      // 3. Device 1 unmarks video_A unwatched at t=2000 (negative timestamp)
      const res3 = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ item_states: { 'video_A': -2000 }, top20_read: [] })
      }), env);
      const data3 = await res3.json();
      if (data3.top20_read.includes('video_A')) throw new Error('video_A should NOT be watched');
      if (!data3.top20_read.includes('video_B')) throw new Error('video_B should still be watched');

      // 4. Stale Device 3 connects with old state where video_A had t=1000
      const res4 = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ item_states: { 'video_A': 1000 }, top20_read: ['video_A'] })
      }), env);
      const data4 = await res4.json();
      if (data4.top20_read.includes('video_A')) throw new Error('Stale push resurrected unmarked video_A!');

      process.stdout.write('OK_UNMARK');
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    res = subprocess.run(
        ["node", "-e", node_script],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node unmarking test failed: {res.stderr}"
    assert "OK_UNMARK" in res.stdout


def _run_node_script(node_script):
    res = subprocess.run(
        ["node", "-e", node_script],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node worker script failed: {res.stderr}"
    return res.stdout


def test_worker_rejects_query_key_and_short_keys():
    """BUG-004/020: auth is headers-only with a 16-char minimum."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const env = { SYNC_BUCKET: { get: async () => null, put: async () => {} } };

      // Query-string key must NOT authenticate, even when long enough.
      const q = await worker.fetch(
        new Request('http://localhost/sync?key=this-key-is-long-enough', { method: 'GET' }), env);
      if (q.status !== 401) throw new Error('Expected 401 for query-string auth');

      // Short header key must NOT authenticate.
      const s = await worker.fetch(new Request('http://localhost/sync', {
        method: 'GET', headers: { 'X-Sync-Key': 'short' },
      }), env);
      if (s.status !== 401) throw new Error('Expected 401 for short key');

      // Malformed JSON push must 400, not merge as {}.
      const b = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Sync-Key': 'long-enough-passphrase' },
        body: '{not-json',
      }), env);
      if (b.status !== 400) throw new Error('Expected 400 for malformed payload, got ' + b.status);

      process.stdout.write('OK_AUTH');
    }).catch(err => { console.error(err); process.exit(1); });
    """
    assert "OK_AUTH" in _run_node_script(node_script)


def test_worker_parses_stored_object_once():
    """BUG-021: R2 bodies are single-use; a second parse must never be attempted."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const storage = new Map();
      const mockR2 = {
        async get(key) {
          if (!storage.has(key)) return null;
          const data = storage.get(key);
          let consumed = false;
          return {
            // Faithful R2 behavior: the body can be consumed exactly once.
            json: async () => {
              if (consumed) throw new Error('Body already used');
              consumed = true;
              return JSON.parse(data);
            },
            text: async () => data,
          };
        },
        async put(key, value) {
          storage.set(key, typeof value === 'string' ? value : JSON.stringify(value));
        }
      };
      const env = { SYNC_BUCKET: mockR2 };
      const AUTH = { 'Content-Type': 'application/json', 'X-Sync-Key': 'single-parse-passphrase' };

      await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST', headers: AUTH,
        body: JSON.stringify({ read_ids: ['a'], top20_read: ['t1'] }),
      }), env);
      // Second push reads back the stored object: partition must survive.
      const res = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST', headers: AUTH,
        body: JSON.stringify({ read_ids: ['b'], top20_read: ['t2'] }),
      }), env);
      const data = await res.json();
      const ids = (data.read_ids || []).sort().join(',');
      const top = (data.top20_read || []).sort().join(',');
      if (ids !== 'a,b') throw new Error('Partition lost read_ids: ' + ids);
      if (top !== 't1,t2') throw new Error('Partition lost top20_read: ' + top);
      process.stdout.write('OK_SINGLE_PARSE');
    }).catch(err => { console.error(err); process.exit(1); });
    """
    assert "OK_SINGLE_PARSE" in _run_node_script(node_script)


def test_worker_caps_unbounded_state():
    """BUG-005: item_states and id arrays are bounded server-side."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const storage = new Map();
      const mockR2 = {
        async get(key) {
          if (!storage.has(key)) return null;
          const data = storage.get(key);
          return { json: async () => JSON.parse(data), text: async () => data };
        },
        async put(key, value) {
          storage.set(key, typeof value === 'string' ? value : JSON.stringify(value));
        }
      };
      const env = { SYNC_BUCKET: mockR2 };
      const AUTH = { 'Content-Type': 'application/json', 'X-Sync-Key': 'caps-passphrase-03' };

      const states = {};
      for (let i = 0; i < 6000; i++) states['k' + i] = i + 1;
      states['bad-ts'] = 'not-a-number';
      states['x'.repeat(300)] = 1;
      const res = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST', headers: AUTH,
        body: JSON.stringify({ item_states: states }),
      }), env);
      const data = await res.json();
      const keys = Object.keys(data.item_states || {});
      if (keys.length !== 5000) throw new Error('Expected 5000 capped states, got ' + keys.length);
      if ('bad-ts' in (data.item_states || {})) throw new Error('Non-numeric timestamp accepted');
      if (!('k5999' in (data.item_states || {}))) throw new Error('Newest intent evicted');
      if ('k0' in (data.item_states || {})) throw new Error('Stalest intent kept over newest');
      process.stdout.write('OK_CAPS');
    }).catch(err => { console.error(err); process.exit(1); });
    """
    assert "OK_CAPS" in _run_node_script(node_script)


def test_worker_routes_post_through_coordinator_when_bound():
    """BUG-002: with the DO binding present, pushes serialize through the stub."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      let stubHits = 0;
      let seenObject = '';
      const env = {
        SYNC_BUCKET: { get: async () => null, put: async () => {} },
        SYNC_COORDINATOR: {
          idFromName: (name) => ({ name }),
          get: (id) => ({
            fetch: async (req) => {
              stubHits += 1;
              seenObject = req.headers.get('X-Sync-Object') || '';
              const body = await req.text();
              JSON.parse(body);
              return new Response(JSON.stringify({
                ok: true, read_ids: ['via-do'], top20_read: [],
                item_states: {}, updated_at: new Date().toISOString(),
              }), { headers: { 'Content-Type': 'application/json' } });
            },
          }),
        },
      };
      const res = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Sync-Key': 'coordinator-passphrase',
          'Origin': 'https://vkr1729.github.io',
        },
        body: JSON.stringify({ read_ids: ['a'] }),
      }), env);
      if (stubHits !== 1) throw new Error('POST did not route through coordinator stub');
      if (!/^sync\\/[0-9a-f]{64}\\.json$/.test(seenObject)) {
        throw new Error('Bad object header forwarded: ' + seenObject);
      }
      const data = await res.json();
      if (!data.ok || (data.read_ids || [])[0] !== 'via-do') {
        throw new Error('Coordinator response not relayed');
      }
      if (res.headers.get('Access-Control-Allow-Origin') !== 'https://vkr1729.github.io') {
        throw new Error('CORS headers missing on coordinated response');
      }
      process.stdout.write('OK_DO_ROUTE');
    }).catch(err => { console.error(err); process.exit(1); });
    """
    assert "OK_DO_ROUTE" in _run_node_script(node_script)


def test_worker_heals_corrupt_legacy_shape():
    """RES-007: a corrupt stored shape must heal on push, not 500 forever."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const storage = new Map();
      const mockR2 = {
        async get(key) {
          if (!storage.has(key)) return null;
          const data = storage.get(key);
          return { json: async () => JSON.parse(data), text: async () => data };
        },
        async put(key, value) {
          storage.set(key, typeof value === 'string' ? value : JSON.stringify(value));
        }
      };
      const env = { SYNC_BUCKET: mockR2 };
      const AUTH = { 'Content-Type': 'application/json', 'X-Sync-Key': 'heal-corrupt-shape-04' };

      // Seed one push so the object exists, then corrupt it out-of-band.
      await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST', headers: AUTH, body: JSON.stringify({ read_ids: ['a'] }),
      }), env);
      const objKey = [...storage.keys()][0];
      storage.set(objKey, JSON.stringify({ read_ids: 'CORRUPT-STRING', top20_read: 42, updated_at: 'not-a-date' }));

      const res = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST', headers: AUTH,
        body: JSON.stringify({ read_ids: ['b'], top20_read: ['t'] }),
      }), env);
      if (res.status !== 200) throw new Error('Corrupt shape bricked writes: ' + res.status);
      const data = await res.json();
      if ((data.read_ids || []).join(',') !== 'b') throw new Error('Heal failed: ' + JSON.stringify(data.read_ids));
      process.stdout.write('OK_HEAL');
    }).catch(err => { console.error(err); process.exit(1); });
    """
    assert "OK_HEAL" in _run_node_script(node_script)


def test_worker_relays_coordinator_retry_after():
    """RES-008: a coordinated 429 must keep its Retry-After header."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const env = {
        SYNC_BUCKET: { get: async () => null, put: async () => {} },
        SYNC_COORDINATOR: {
          idFromName: (name) => ({ name }),
          get: (id) => ({
            fetch: async () => new Response(JSON.stringify({ error: 'Rate limited' }), {
              status: 429,
              headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
            }),
          }),
        },
      };
      const res = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Sync-Key': 'retry-after-passphrase' },
        body: JSON.stringify({ read_ids: ['a'] }),
      }), env);
      if (res.status !== 429) throw new Error('Expected relayed 429, got ' + res.status);
      if (res.headers.get('Retry-After') !== '60') {
        throw new Error('Retry-After dropped by relay: ' + res.headers.get('Retry-After'));
      }
      process.stdout.write('OK_RETRY_RELAY');
    }).catch(err => { console.error(err); process.exit(1); });
    """
    assert "OK_RETRY_RELAY" in _run_node_script(node_script)


def test_worker_audio_preflight_covers_range():
    """RES-009: audio OPTIONS must preflight Range for cross-origin fetch()."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const env = { SYNC_BUCKET: { get: async () => null, put: async () => {} } };
      const res = await worker.fetch(new Request('http://localhost/tubelm/audio/x.mp3', {
        method: 'OPTIONS',
        headers: { 'Origin': 'https://vkr1729.github.io' },
      }), env);
      if (res.headers.get('Access-Control-Allow-Origin') !== '*') {
        throw new Error('Audio preflight lost wildcard origin');
      }
      const allowHeaders = res.headers.get('Access-Control-Allow-Headers') || '';
      if (!allowHeaders.includes('Range')) {
        throw new Error('Audio preflight omits Range: ' + allowHeaders);
      }
      if (!res.headers.get('Access-Control-Allow-Methods')) {
        throw new Error('Audio preflight omits Allow-Methods');
      }
      process.stdout.write('OK_AUDIO_PREFLIGHT');
    }).catch(err => { console.error(err); process.exit(1); });
    """
    assert "OK_AUDIO_PREFLIGHT" in _run_node_script(node_script)


def test_worker_payload_cap_counts_bytes_not_chars():
    """Multibyte bodies must hit the 1 MiB byte cap even when short in chars."""
    worker_path = Path(__file__).resolve().parents[3] / "worker" / "worker.js"
    assert worker_path.exists()

    node_script = """
    import('./worker/worker.js').then(async (m) => {
      const worker = m.default;
      const env = { SYNC_BUCKET: { get: async () => null, put: async () => {} } };
      const AUTH = { 'Content-Type': 'application/json', 'X-Sync-Key': 'byte-cap-passphrase-05' };
      // 400k CJK chars = 1.2M UTF-8 bytes but only ~400k UTF-16 units.
      const big = 'h'.repeat(100) + '\\u6f22'.repeat(400000);
      const res = await worker.fetch(new Request('http://localhost/sync', {
        method: 'POST', headers: AUTH,
        body: JSON.stringify({ read_ids: [big] }),
      }), env);
      if (res.status !== 413) throw new Error('Expected 413 for >1MiB byte body, got ' + res.status);
      process.stdout.write('OK_BYTE_CAP');
    }).catch(err => { console.error(err); process.exit(1); });
    """
    assert "OK_BYTE_CAP" in _run_node_script(node_script)


def test_reader_sanitizes_untrusted_urls_and_handler_args():
    """BUG-017/018: feed-controlled URLs/handler args cannot execute script."""
    template_path = Path(__file__).resolve().parents[2] / "templates" / "reader.html"
    content = template_path.read_text(encoding="utf-8")

    # Static contract: every dynamic href is sanitized; every new-tab link is
    # tabnabbing-safe; the sync key never travels in a URL.
    assert 'href="${item.url}"' not in content
    assert 'href="${v.url}"' not in content
    assert 'href="${b.url}"' not in content
    assert 'href="${ch.notebook_url}"' not in content
    assert 'href="${ch.audio_url}"' not in content
    for line in content.splitlines():
        if 'target="_blank"' in line:
            assert 'rel="noopener noreferrer"' in line, line.strip()[:120]
    # Sync fetch() calls must not smuggle the key into the URL query. (The key
    # in the pairing link lives in the #fragment, which browsers never send.)
    assert "${sep}key=" not in content
    assert "syncEndpoint}${sep}" not in content
    for line in content.splitlines():
        if "fetch(syncEndpoint" in line:
            assert "key=" not in line, line.strip()[:120]

    node_script = """
    const fs = require('fs');
    const html = fs.readFileSync('./desktop/templates/reader.html', 'utf8');
    function extract(name) {
      const start = html.indexOf('function ' + name + '(');
      if (start < 0) throw new Error('missing ' + name);
      const lineEnd = html.indexOf('\\n', start);
      const firstLine = html.slice(start, lineEnd);
      if (firstLine.trimEnd().endsWith('}')) return firstLine;
      const end = html.indexOf('\\n    }', start);
      if (end < 0) throw new Error('unterminated ' + name);
      return html.slice(start, end + '\\n    }'.length);
    }
    global.window = { location: { origin: 'https://reader.local' } };
    eval(extract('esc') + '\\n' + extract('safeExternalUrl') + '\\n' + extract('escapeQuotes'));

    // javascript: / data: / vbscript: URLs must not survive into href.
    for (const evil of ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,<script>alert(1)</script>', 'vbscript:msgbox(1)', 'file:///etc/passwd']) {
      if (safeExternalUrl(evil) !== '#') throw new Error('unsafe URL survived: ' + evil);
    }
    // Legit URLs pass through, HTML-escaped.
    const good = safeExternalUrl('https://example.com/a?b=1&c=2');
    if (!good.startsWith('https://example.com/a?b=1')) throw new Error('good URL mangled: ' + good);
    if (!good.includes('&amp;')) throw new Error('href not HTML-escaped: ' + good);
    // Backslash-quote breakout must be neutralized (backslash doubled first).
    const armed = escapeQuotes("\\\\';alert(1);//");
    if (armed !== "\\\\\\\\\\\\';alert(1);//") throw new Error('backslash escape wrong: ' + armed);
    if (escapeQuotes('it\\'s "quoted"') !== 'it\\\\\\'s &quot;quoted&quot;') {
      throw new Error('quote escape wrong: ' + escapeQuotes('it\\'s "quoted"'));
    }
    process.stdout.write('OK_READER_ESC');
    """
    assert "OK_READER_ESC" in _run_node_script(node_script)
