# FINN — Build History Index

This directory contains the authentic, unedited agent trajectory logs for the entire FINN build and verification process, with all credentials redacted.

## Index of Files

| File | Description | Size |
|---|---|---|
| [`transcript.jsonl`](transcript.jsonl) | Compact step-by-step agent execution log (user prompts, model reasoning, tool invocations). | ~2.3 MB |
| [`transcript_full.jsonl`](transcript_full.jsonl) | Full unabridged agent execution log including full tool outputs and thinking steps. | ~3.8 MB |
| [`SECRETS_SCAN.md`](SECRETS_SCAN.md) | Automated regex security verification report across all transcripts and repository files. | ~1 KB |

## Build Trajectory Summary
- **Session 1 (Phase 1–2)**: Next.js scaffold, ticker verification, initial integrity reset (purged invented demo data), BSE vs NSE corporate announcement fetcher via `curl_cffi`, Slice 1 results PDF table extraction (`pypdfium2` vision fallback), Schedule III Operating EBITDA derivation, and bank format handling.
- **Session 2 (Phase 3–4)**: Multi-quarter concall transcript + results fetcher, Citation Gate v3 implementation (zero page tolerance, number-in-quote rule, chronological guard), 12/12 adversarial negative test suite, 100% announcement ingestion, URL & period attachment fix, configurable alert settings panel, and mobile 390px audit.
- **Session 3 (Phase 5)**: PDF git pack scrubbing via `git filter-repo`, repository hygiene audit, executive covering note, and final verification.
