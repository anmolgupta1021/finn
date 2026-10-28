# FINN — Secrets & Credentials Scan Report

Date: 2026-10-28
Tool: Automated Security Audit (Regex & Exact Value Scanner)

## 1. Scanner Patterns
- **Actual Key Value from `.env`**: Scanned for the exact value of `GEMINI_API_KEY` (length: 53 characters).
- **Google Gemini API Key Pattern**: `AIza[0-9A-Za-z\-_]{35}`
- **Google Antigravity / Vertex Token Pattern**: `AQ\.[A-Za-z0-9_\-]{10,}`
- **GitHub Personal Access Token Pattern**: `ghp_[0-9A-Za-z]{36}`
- **Generic RSA/OpenSSH Private Key Headers**: `-----BEGIN (?:RSA )?PRIVATE KEY-----`

## 2. Scan Results by Target

| Target File | Status | Matches Found |
|---|---|---|
| `build_history/transcript.jsonl` | **PASS** | 0 secrets (4 instances of API keys redacted to `[REDACTED_API_KEY]`) |
| `build_history/transcript_full.jsonl` | **PASS** | 0 secrets (8 instances of API keys redacted to `[REDACTED_API_KEY]`) |
| `build_history/LOG.md` | **PASS** | 0 secrets |
| `COVERING_NOTE.md` | **PASS** | 0 secrets |
| `DECISIONS.md` | **PASS** | 0 secrets |
| `README.md` | **PASS** | 0 secrets |
| Git History (`git log -p`) | **PASS** | 0 secrets |

## 3. Environment & Local Configuration
- `.env`: Present in `.gitignore` and untracked in git index (`git status --ignored`).
- `.env.example`: Committed with safe placeholder `GEMINI_API_KEY=your_gemini_api_key_here`.
