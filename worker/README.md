# TubeLM Cross-Device State Sync Worker

This Cloudflare Worker synchronizes your TubeLM watch history and channel read states across your phone, laptop, and workplace devices using your existing Cloudflare R2 storage bucket.

---

## Architecture & Security

- **Storage:** Persisted directly into your Cloudflare R2 bucket under `sync/<sha256_hash>.json`.
- **Zero Exposed Cloud Credentials:** Your Cloudflare API tokens and secret keys never touch client-side browsers or GitHub Pages.
- **Additive Merge (CRDT-lite):** Concurrent reads and watched videos from multiple devices are merged as a Set Union so neither device overwrites the other.
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
   - **Sync Passphrase:** Choose any private passphrase (e.g. `kedar-sync-2026`).
4. Click **Save & Sync Now**.
5. Click **Copy Mobile Pairing Link** (or scan the QR code).
6. Open the link on your phone. It pairs automatically in one click!
