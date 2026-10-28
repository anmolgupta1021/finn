# FINN — Secrets & Credentials Scan Report

Date: 2026-10-28
Tool: Automated Regex Security Audit

## 1. Git History Audit (`git log -p`)
Scanned all commit diffs in git history for:
- Google Gemini API Keys (`AIza...`)
- GitHub Personal Access Tokens (`ghp_...`)
- RSA/OpenSSH Private Keys
- Vercel API Tokens
- Hardcoded `GEMINI_API_KEY` assignments

**Result**: `PASS` — 0 secrets found across all commits in repository history.

## 2. Environment File Check
- `.env`: Verified present in `.gitignore` and untracked in git index (`git status --ignored`).
- `.env.example`: Committed with dummy placeholder `GEMINI_API_KEY=your_gemini_api_key_here`.

## 3. Large File & Document Check
- `data/documents/`: Added to `.gitignore` and untracked from git index (`git rm -r --cached data/documents`).
- Note on PDF objects in git pack: See `DECISIONS.md` on historical pack objects and repo clean options prior to first public remote push.
