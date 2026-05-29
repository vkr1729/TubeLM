<p align="center">
  <img src="shared/assets/logo.png" alt="TubeLM Logo" width="220px">
</p>

# 🎬 TubeLM — Premium YouTube to NotebookLM Automation Pipeline & Email Digest

[![GitHub Stars](https://img.shields.io/github/stars/vkr1729/TubeLM?style=social)](https://github.com/vkr1729/TubeLM/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS-lightgrey)](https://www.kernel.org/)
[![Built with NotebookLM-py](https://img.shields.io/badge/built%20with-notebooklm--py-blueviolet)](https://github.com/leptonai/notebooklm-py)

**TubeLM** is a production-grade, self-hosted automation pipeline that monitors your favorite YouTube channels, fetches new uploads, and programmatically uploads them to Google's **NotebookLM**. It orchestrates NotebookLM to extract high-yield, citation-clean intelligence summaries, generate custom infographics, trigger podcast Audio Overviews, and deliver a **stunning, dark-mode cinematic HTML newsletter** straight to your inbox.

Designed for busy executives, researchers, developers, and creators who need maximum intelligence from video uploads without spending hours watching streams or dealing with noisy subscription feeds.

---

## 🚀 One-Click Desktop Apps (Windows, macOS, & Linux)

For non-technical users who want to run the TubeLM Web Dashboard **without** using the command line, cloning Git, or installing Python manually:

| macOS (Apple Silicon/Intel) | Windows (10/11) | Linux (Ubuntu/Debian) |
| :---: | :---: | :---: |
| [![Download macOS](https://img.shields.io/badge/Download-macOS%20App-blue?style=for-the-badge&logo=apple)](https://github.com/vkr1729/TubeLM/releases/latest) | [![Download Windows](https://img.shields.io/badge/Download-Windows%20App-blue?style=for-the-badge&logo=windows)](https://github.com/vkr1729/TubeLM/releases/latest) | [![Download Linux](https://img.shields.io/badge/Download-Debian%20%2F%20Ubuntu-blue?style=for-the-badge&logo=ubuntu)](https://github.com/vkr1729/TubeLM/releases/latest) |
| **`TubeLM-macOS.zip`** | **`TubeLM-Windows.zip`** | **`tubelm_1.0.0_amd64.deb`** |

### 🍏 macOS Quick Start:
1. **Download:** Get `TubeLM-macOS.zip` from the [Latest Releases](https://github.com/vkr1729/TubeLM/releases/latest).
2. **Unzip:** Extract the `.zip` file on your Mac.
3. **Launch:** Double-click the native **`TubeLM.app`** status bar app! It will silently run in your menu bar (showing a native `📺` icon) and auto-open the dashboard in your default browser.

### 🪟 Windows Quick Start:
1. **Download:** Get `TubeLM-Windows.zip` from the [Latest Releases](https://github.com/vkr1729/TubeLM/releases/latest).
2. **Unzip:** Extract the folder to a safe place (e.g., your Desktop).
3. **Launch:** Double-click the **`TubeLM.exe`** status tray app! It will run in your Windows system taskbar tray (showing a native status icon) and automatically launch the dashboard in your browser.

### 🐧 Ubuntu / Debian Quick Start:
1. **Download:** Get the `tubelm_1.0.0_amd64.deb` installer from the [Latest Releases](https://github.com/vkr1729/TubeLM/releases/latest).
2. **Install:** Double-click the `.deb` package to open Ubuntu Software Center and click **Install**, or run:
   ```bash
   sudo dpkg -i tubelm_1.0.0_amd64.deb
   ```
3. **Launch:** Open your applications menu, search for **TubeLM**, and click the icon to launch!

---

## 📸 Visual Preview

### 🖥️ Local Web Dashboard GUI
Experience a premium, glassmorphic dark-theme control panel to monitor active subscriptions, edit channel timestamps inline, manage Google session cookies, and batch-delete workspaces in parallel:

![TubeLM Local Web Dashboard](shared/assets/gui_dashboard.png)

---

### 📱 Premium Mobile Email Digest (Markets by Zerodha)
Delivers a publication-grade, mobile-optimized HTML newsletter optimized for Gmail/iOS with cinema-style dark cards, high-yield bullet metrics, and native, high-resolution infographics:

| 1. Header & Infographic | 2. Video Card & Thesis | 3. Hard Data Points |
| :---: | :---: | :---: |
| ![Header & Infographic](shared/assets/email_preview_header.jpg) | ![Video Card & Thesis](shared/assets/email_preview_thesis.jpg) | ![Bullet Highlights](shared/assets/email_preview_data.jpg) |

---

## 🖥️ Local Web Dashboard (GUI)

TubeLM features a premium, glassmorphic local web dashboard to manage your YouTube automation pipeline directly in your browser. The GUI installation is **enabled by default** and serves as the primary way to interact with the pipeline.

### 1. Launching the Dashboard

If installed via the `setup.sh` wizard in **GUI Mode** (default), launch the dashboard with:
```bash
.venv/bin/python main.py --gui
```
This launches a local web server at `http://localhost:5000` (which dynamically falls back to the next available port if `5000` is already in use) and automatically opens a tab in your default browser.

### 2. Dashboard Features

* **📊 Dashboard Overview:** Monitor active subscriptions, check local Google Account session cookies, trigger cookie cache refreshes, and inspect timer logs.
* **📒 NotebookLM Workspaces Manager:**
  * Displays all notebooks on your Google Account grouped by monitored YouTube channel, sorted by date.
  * Allows **manual selection and parallel bulk deletion** using checkboxes and the `Delete Selected (N)` button.
  * Toggles **Select All per Channel** groups or uncategorized groups with modern indeterminate UI support.
* **🚀 Selective Run & Live Logs Console:**
  * View lookback date/time timestamps for each YouTube channel individually.
  * **Edit last run timestamps inline** with a datetime picker or reset them to default lookback windows.
  * Run the pipeline selectively for specific checked channels (e.g. `Physionic` or `Markets by Zerodha`).
  * Watch output logs stream line-by-line in real time via Server-Sent Events (SSE).
* **📺 Monitored Channels:** Add or delete YouTube channels dynamically from the dashboard.
* **⚙️ Configuration & Secrets Editor:** Save email settings, API credentials, and retention rules (e.g. `NOTEBOOKS_RETENTION_LIMIT` to retain the N latest notebooks per channel and auto-prune older ones) directly to `.env`.
* **📅 Automation Controller (Weekly Scheduler):**
  * View whether the background automation timer is enabled or disabled.
  * **Schedule the weekly run** directly from the GUI by selecting a custom **Day of the Week** and **Time** (e.g., Monday at 14:30).
  * Update the active systemd timer dynamically at any time with a single click.
* **📝 Prompts Customizer:** Live-edit research summaries (`Summary_Prompt.md`) and podcast templates (`Podcast_Prompt.md`).
* **📁 Historical Digests Library:** View and read past generated HTML briefings directly in your browser.

---

## 🚀 Key Features

*   **📰 Automated RSS Channel Monitoring:** Regularly polls YouTube RSS feeds for new uploads based on custom lookback schedules.
*   **🛡️ Short-form & Spam Filters:** Aggressively filters out TikTok-style Shorts and hashtag spam using multi-layer heuristics (video length verify checks via YouTube API, `#shorts` tag filters, and title structure analysis).
*   **🧠 Programmatic NotebookLM Orchestration:**
    *   Creates isolated, dedicated notebooks for each monitored YouTube channel.
    *   Uploads video URLs asynchronously as grounded sources.
    *   Instructs NotebookLM to synthesize cross-source insights using custom research prompts.
    *   Generates and downloads structural visual infographics.
    *   Triggers background generation of audio podcasts (NotebookLM Audio Overviews).
*   **✉️ Cinema-Style HTML Digests:**
    *   Delivers responsive dark-mode emails featuring native `<img>` thumbnails (mobile-safe layout verified in Gmail & Apple Mail).
    *   Displays video summaries directly below each individual video card for quick scannability.
    *   Zero-dependency markdown parser formats headers, bullet points, and key metrics.
    *   Cleans and strips AI citation numbers (e.g. `[12-15]`) for peak text scannability.
*   **⏰ Saturday Boot & Automation Daemon:** Sets up a persistent local background daemon via systemd user timers. If your machine is off during the scheduled Saturday run, the timer triggers **immediately upon boot** once network connectivity is verified.

---

## ⚖️ Why TubeLM?

Most AI-powered YouTube newsletter summaries rely on OpenAI GPT-4 or Anthropic Claude APIs, which can become expensive for long-form video transcripts and lack cross-document grounding.

| Feature | **TubeLM** (NotebookLM) | Standard LLM Summarizers (GPT/Claude API) |
| :--- | :--- | :--- |
| **API Token Cost** | 💰 **$0 (Zero Token Fees)** | 📈 High (billed per-token for long transcripts) |
| **Workspace Grounding** | **Yes** (accumulates sources in a shared notebook) | **No** (stateless API queries) |
| **Audio Overview / Podcasts** | **Yes** (auto-generates standard 2-host audio) | **No** (requires separate audio generation APIs) |
| **Mobile-Optimized Layout** | **Yes** (Cinema dark mode, native Gmail-safe images) | **No** (usually basic plain text or generic markdown) |
| **Privacy First** | **Yes** (Local systemd daemon, credentials in `.env`) | **No** (Requires uploading data to third-party services) |

---

## 🛠️ Installation & Setup

### 1. Prerequisites

*   **Linux / macOS** (systemd is used for the automated weekly scheduler; macOS users can adapt to launchd).
*   **Python 3.10+** (with virtual environment).
*   **Google Chrome** (you must be logged in to your Google Account in Chrome, as cookies are extracted dynamically from your local Chrome profile).

### 2. Interactive Setup Wizard

TubeLM provides an interactive setup script that automatically sets up your virtual environment and installs the required packages.

Clone the repository and run the setup wizard:
```bash
git clone https://github.com/vkr1729/TubeLM.git
cd TubeLM
./setup.sh
```

During installation, you can choose between:
* **Option 1: GUI Mode (Default & Recommended):** Installs all core dependencies and additional packages for the local Web Dashboard GUI.
* **Option 2: Core Only Mode:** A lightweight setup that installs only the core pipeline engine, skipping Flask web dependencies.

### 3. Basic Configuration

1. **Environment Config (`.env`):**
   Copy the example template and fill in your details:
   ```bash
   cp .env.example .env
   nano .env
   ```

2. **Channel Config (`channels.json`):**
   Define the channels you want to monitor (we recommend keeping your personal channel list private and adding `channels.json` to `.gitignore`):
   ```bash
   cp channels.json.example channels.json
   nano channels.json
   ```

   ```json
   [
     { "name": "Physionic", "channel_id": "UCj3p_1jOCJXB_L_we-DjLbA" },
     { "name": "Doctor Brad Stanfield", "channel_id": "UCZ0zZ_A30TDFn9-K_n-mP2g" }
   ]
   ```

---

## 🔋 Zero-Credential Standalone Local Mode

TubeLM supports a fully offline, **zero-credential local mode**. You do not need to register for Google Cloud APIs or set up custom SMTP servers to use TubeLM. 

If `YOUTUBE_API_KEY` is not provided and SMTP configurations are omitted/empty in your `.env` file:
1. **API Key Bypassed:** TubeLM will skip duration-based video checks (Layer 3) and instead rely on title and tag heuristics to filter out short-form spam.
2. **SMTP Bypassed:** SMTP authentication checks are skipped entirely and no email is sent.
3. **Local Digests Saved:** TubeLM executes the full intelligence analysis pipeline and writes the outputs directly to the local directory:
   - **Markdown Digests:** Written to `summaries/{run_date}_digest.md`.
   - **Cinematic HTML Digests:** Written to `summaries/{run_date}_{channel_name}_digest.html`.

You can view these offline briefs directly in your browser or Markdown reader at any time, allowing you to use TubeLM completely locally and privately out of the box!

---

## ⚙️ Background Automation (systemd user timer)

TubeLM can run as a persistent background daemon that checks for new uploads and processes them on a regular schedule.

### 1. Quick GUI Scheduling (Recommended)
Launch the **Local Web Dashboard**, go to **Config** (or the main controller card), select your preferred **Day of Week** and **Time**, and click **Setup Scheduler Daemon**. The system will dynamically generate and register the user systemd files for you!

### 2. Manual Config (Alternative)
To schedule the runs manually:

1. Write a user service file at `~/.config/systemd/user/youtube-digest.service`:
   ```ini
   [Unit]
   Description=TubeLM Weekly Briefing Sync Service
   After=network-online.target

   [Service]
   Type=oneshot
   ExecStart=/home/YOUR_USER/youtube-project-2/scripts/run_weekly.sh
   StandardOutput=journal
   StandardError=journal
   ```

2. Write a user timer file at `~/.config/systemd/user/youtube-digest.timer` (adjusting Day of Week and Time under `OnCalendar` as desired):
   ```ini
   [Unit]
   Description=Run TubeLM Weekly Sync

   [Timer]
   OnCalendar=Sat *-*-* 08:00:00
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```

3. Enable and start the timer daemon:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now youtube-digest.timer
   ```

---

## 💻 CLI Usage (Non-GUI Core)

For headless or keyboard-driven workflows, you can run the pipeline directly from the command line:

```bash
# Run the full pipeline for all channels
.venv/bin/python main.py

# Run for a specific subset of YouTube channel IDs
.venv/bin/python main.py --channels "UCj3p_1jOCJXB_L_we-DjLbA,UCZ0zZ_A30TDFn9-K_n-mP2g"

# Run the pipeline but skip email delivery (saves summaries locally)
.venv/bin/python main.py --skip-email

# Dry-run: discover videos only, skip all AI calls and uploads
.venv/bin/python main.py --dry-run
```

---

## 🗺️ System Flow Architecture

```mermaid
graph TD
    A[Start: Schedule Trigger / Manual Run] --> B[Wait for Wi-Fi Connectivity]
    B --> C[Extract Chrome Session Cookies using rookiepy]
    C --> D[Fetch YouTube RSS Feeds]
    D --> E[Filter out Shorts & Hashtag Spams]
    E --> F{YOUTUBE_API_KEY set?}
    F -- Yes --> G[Verify Video Length via YouTube API]
    F -- No --> H[Skip Duration Checks Heuristics Only]
    G --> I[Initialize NotebookLM Client]
    H --> I
    I --> J[For each channel: Create Notebook & Upload Sources]
    J --> K[Query Chat for Structured Briefing]
    K --> L[Generate & Download Infographic PNG]
    L --> M[Trigger Podcast Audio Overview]
    M --> N[Format Summaries & Strip Citations]
    N --> O[Write Local Markdown & Cinematic HTML digests to /summaries]
    O --> P{SMTP Settings Configured?}
    P -- Yes --> Q[SMTP SSL/STARTTLS Email Delivery]
    P -- No --> R[Skip Email Delivery, Log Warning]
    Q --> S[Update state.json]
    R --> S[Update state.json]
```

---

## 💬 Frequently Asked Questions (FAQ)

### Is there an official NotebookLM API?
No, Google does not provide an official API for NotebookLM. TubeLM automates interactions securely through a Python automation interface utilizing cookie extraction (`rookiepy`) from your local logged-in Chrome profile.

### How are cookies handled? Is it secure?
All authentication is handled locally. TubeLM extracts the active Google NotebookLM session cookie from your machine's Chrome database. It does not store, request, or transmit your Google password or credentials to any third party.

### Can I customize the prompts?
Absolutely. The structure and style of the summaries and podcasts are driven by two Markdown files in the root folder:
*   [Summary_Prompt.md](Summary_Prompt.md): Configures the bullet structure, clinical/tech highlights, and key thesis sections.
*   [Podcast_Prompt.md](Podcast_Prompt.md): Modifies the tone, conversational layout, and dynamic of the two-host Audio Overview.

### Does this cost anything to run?
No. Unlike standard pipelines that charge you per-token to send transcripts to GPT-4, Google NotebookLM is completely free, meaning you can summarize hours of long-form video content without incurring API fees.

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more details.
