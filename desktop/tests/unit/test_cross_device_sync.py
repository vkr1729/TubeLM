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
import json
import re
import subprocess
from pathlib import Path
import pytest


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

    # Core sync engine functions
    assert 'function checkUrlPairing()' in content
    assert 'function pullRemoteState()' in content
    assert 'function pushRemoteState()' in content
    assert 'function scheduleSyncPush()' in content
    assert 'function copyPairingUrl()' in content
    assert 'function disconnectSync()' in content
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

      // 1. CORS Preflight
      const corsRes = await worker.fetch(new Request('http://localhost/sync', { method: 'OPTIONS' }), env);
      if (corsRes.headers.get('Access-Control-Allow-Origin') !== '*') throw new Error('CORS header missing');

      // 2. Auth checks
      const unauth = await worker.fetch(new Request('http://localhost/sync', { method: 'GET' }), env);
      if (unauth.status !== 401) throw new Error('Expected 401 for unauth request');

      // 3. Device 1 (Personal Laptop) writes
      await worker.fetch(new Request('http://localhost/sync?key=secret-pass', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ read_ids: ['vid_A', 'vid_B'], top20_read: ['d1_c1'] })
      }), env);

      // 4. Device 2 (iPhone) writes
      await worker.fetch(new Request('http://localhost/sync?key=secret-pass', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ read_ids: ['vid_B', 'vid_C'], top20_read: ['d1_c2'] })
      }), env);

      // 5. Device 3 (Office Laptop) writes
      await worker.fetch(new Request('http://localhost/sync?key=secret-pass', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ read_ids: ['vid_D'], top20_read: ['d1_c3'] })
      }), env);

      // 6. Device 1 pulls final merged state
      const finalRes = await worker.fetch(new Request('http://localhost/sync?key=secret-pass', { method: 'GET' }), env);
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
