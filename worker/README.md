# TubeLM Cross-Device State Sync Worker

This Cloudflare Worker synchronizes your TubeLM watch history and channel read states across your phone, laptop, and workplace devices using your existing Cloudflare R2 storage bucket.

---

## Architecture & Security

- **Storage:** Persisted directly into your Cloudflare R2 bucket under `sync/<sha256_hash>.json`.
- **Zero Exposed Cloud Credentials:** Your Cloudflare API tokens and secret keys never touch client-side browsers or GitHub Pages.
- **Passphrase (min 16 chars, headers-only):** Your sync passphrase is sent only in the `Authorization`/`X-Sync-Key` headers — never in the URL — and hashed to derive your private namespace. Key knowledge equals read+write access, so treat it as a credential: use 16+ characters and pick a new one (re-pair devices) if it ever leaks.
- **Serialized Merge (Durable Object + LWW):** Concurrent pushes for one passphrase queue through a Durable Object, then merge as signed-timestamp last-writer-wins, so simultaneous devices cannot silently drop each other's state.
- **Bounded State:** Pushes are capped (1 MiB payload, 5000 state entries keeping newest intent) and rate-limited; browser calls are accepted only from the reader origin (`https://vkr1729.github.io`), localhost, and `ALLOWED_ORIGINS`.
- **Enterprise / Workplace Safe:** Payload consists purely of public YouTube IDs and channel timestamps. If accessed from behind strict enterprise firewalls that block unfamiliar endpoints, the web reader silently falls back to local storage without throwing errors.

---

## 2-Minute Deployment Guide

### Prerequisites
- Node.js (v18+)
- Cloudflare Account (same one where your R2 bucket exists)

### Step 1: Login to Cloudflare
In this directory:
```bash
cd worker
npx wrangler login
```

### Step 2: Deploy to Cloudflare
```bash
npx wrangler deploy
```

Wrangler will output your live worker URL, for example:
`https://tubelm-sync.<your-subdomain>.workers.dev`

### Step 3: Connect Devices
1. Open [https://vkr1729.github.io/TubeLM/](https://vkr1729.github.io/TubeLM/) on your laptop.
2. Click the **Cloud Sync** icon in the top header.
3. Enter:
   - **Worker URL:** `https://tubelm-sync.<your-subdomain>.workers.dev`
   - **Sync Passphrase:** Choose a private passphrase of **at least 16 characters** (e.g. `kedar-tubelm-sync-2026`). Shorter keys are rejected with HTTP 401.
4. Click **Save & Sync Now**.
5. Click **Copy Mobile Pairing Link** (or scan the QR code).
6. Open the link on your phone. It pairs automatically in one click!

---

## Migrating from a short (<16 char) passphrase

Keys shorter than 16 characters are rejected (HTTP 401) on every endpoint, so a
namespace created under the old 4-character minimum is unreachable via the API
until it is moved. Your data is still in R2 at `sync/<sha256(old-key)>.json` —
move it to the new key's object with wrangler:

```bash
OLD=$(echo -n 'your-old-passphrase' | sha256sum | cut -d' ' -f1)
NEW=$(echo -n 'your-new-16-plus-passphrase' | sha256sum | cut -d' ' -f1)
wrangler r2 object get tubelm/sync/$OLD.json --file /tmp/tubelm-sync-state.json
wrangler r2 object put tubelm/sync/$NEW.json --file /tmp/tubelm-sync-state.json
rm /tmp/tubelm-sync-state.json
```

Then re-pair every device with the new passphrase. (Replace `tubelm` with your
`R2_BUCKET_NAME` if it differs.)
