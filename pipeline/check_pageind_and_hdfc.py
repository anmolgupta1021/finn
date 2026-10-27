"""
Inspect Page 3 of PAGEIND_Q1FY27.pdf (why it mentions consolidated)
and test downloading the actual NSE URL for HDFCBANK Q2 FY27 results:
https://nsearchives.nseindia.com/corporate/HDFCBANK_17102026135520_OutcomeofBMResults_17oct2026.pdf
"""
from __future__ import annotations

import pdfplumber
from config import DOCS_DIR
from fetch_announcements import create_nse_session


def main() -> None:
    pdf_path = DOCS_DIR / "results" / "PAGEIND_Q1FY27.pdf"
    with pdfplumber.open(pdf_path) as pdf:
        print("=== PAGEIND_Q1FY27.pdf PAGE 3 FULL TEXT ===")
        print(pdf.pages[2].extract_text())

    sess = create_nse_session()
    alt_url = "https://nsearchives.nseindia.com/corporate/HDFCBANK_17102026135520_OutcomeofBMResults_17oct2026.pdf"
    print(f"\n=== TESTING ALTERNATE NSE URL: {alt_url} ===")
    r = sess.get(alt_url, headers={"Accept-Encoding": "identity"}, timeout=30)
    print(f"HTTP {r.status_code} | Content-Length: {r.headers.get('Content-Length')} | Actual bytes: {len(r.content)}")
    print(f"First 16 bytes: {r.content[:16]!r} | Last 32 bytes: {r.content[-32:]!r}")

    # Also test Range request if truncated
    cl = int(r.headers.get("Content-Length") or 0)
    if len(r.content) < cl:
        r_range = sess.get(alt_url, headers={"Range": f"bytes={len(r.content)}-"}, timeout=30)
        print(f"Range bytes={len(r.content)}-: HTTP {r_range.status_code} | Content-Range: {r_range.headers.get('Content-Range')} | Bytes: {len(r_range.content)}")


if __name__ == "__main__":
    main()
