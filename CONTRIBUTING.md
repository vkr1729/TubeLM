# Contributing to YouTube → NotebookLM Weekly Briefing Sync

We welcome community contributions! To ensure high-quality contributions and maintain coding standards, please follow these guidelines:

## 🤝 Code of Conduct

Be respectful, constructive, and professional in all communications.

## 🐛 Reporting Bugs & Suggesting Features

*   **Search First:** Check open and closed Issues to see if your problem has already been reported.
*   **Use Templates:** Use our Bug Report or Feature Request templates when opening a new Issue.
*   **Provide Context:** Include system details, logs (stripping out any credentials or personal email addresses), and steps to reproduce.

## 🛠️ Pull Request Process

1.  **Fork the Repository:** Create a personal fork and create a branch from `main`.
2.  **Coding Standards:**
    *   Write clean, well-documented code.
    *   Maintain strict **Surgical** editing principles (do not change unrelated files or formats).
    *   Follow **Crash-Early** rules: do not catch exceptions silently. Always log exceptions with full details.
3.  **Run Syntax/Verification Check:**
    Ensure all files compile cleanly:
    ```bash
    python -m py_compile email_service.py config.py main.py notebooklm_service.py
    ```
4.  **Submit PR:** Open a Pull Request targeting the `main` branch. Provide a clear description of the problem solved and test results.
