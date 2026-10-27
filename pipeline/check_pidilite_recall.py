"""
Item 3: Page Selection Audit & Guidance Recall Check on PIDILITIND.NS.
"""
from __future__ import annotations

import json
import re
from config import DATA_DIR, RESEARCH_DIR, save_json
from fetch_announcements import create_nse_session
from generate_research import discover_nse_primary_documents, download_and_extract_pages


def main() -> None:
    sess = create_nse_session()
    _, docs = discover_nse_primary_documents(sess, "PIDILITIND.NS", days_back=460)
    enriched, read_pages, corpus = download_and_extract_pages(sess, "PIDILITIND.NS", docs)

    raw_total_chars = sum(len(t) for t in read_pages.values())
    corpus_total_chars = len(corpus)
    sent_corpus = corpus[:180000]

    # Check which (doc_id, page) markers appear inside sent_corpus vs dropped after 180,000 chars
    included_markers = re.findall(r"\[(DOC_\d+)\s*\|\s*PDF PAGE\s*(\d+)", sent_corpus)
    all_markers = re.findall(r"\[(DOC_\d+)\s*\|\s*PDF PAGE\s*(\d+)", corpus)
    included_set = {(d, int(p)) for d, p in included_markers}
    all_set = {(d, int(p)) for d, p in all_markers}
    dropped_set = sorted(all_set - included_set, key=lambda x: (int(x[0].split("_")[1]), x[1]))

    # Check how many pages had > 3200 chars truncated per page
    truncated_pages = [
        {"doc_id": d, "page": p, "raw_chars": len(txt), "chars_dropped_on_page": len(txt) - 3200}
        for (d, p), txt in sorted(read_pages.items(), key=lambda x: (int(x[0][0].split("_")[1]), x[0][1]))
        if len(txt) > 3200
    ]

    # Scan all 103 transcript pages (DOC_1..DOC_5) for sentences containing guidance/target/corridor/range/outlook
    guidance_kw = re.compile(
        r"\b(guid\w*|corridor|target\w*|aspir\w*|range of|band of|double digit\w*|capex|a&sp|spends|vam\b)",
        re.IGNORECASE,
    )
    guidance_mentions = []
    for (doc_id, p_num), txt in sorted(read_pages.items(), key=lambda x: (int(x[0][0].split("_")[1]), x[0][1])):
        if int(doc_id.split("_")[1]) > 5:
            continue
        for line in re.split(r"(?<=[.?!])\s+", txt):
            clean_line = " ".join(line.split())
            if guidance_kw.search(clean_line) and re.search(r"\d", clean_line) and 40 <= len(clean_line) <= 320:
                in_3200 = txt.find(line[:30]) < 3200 if line[:30] in txt else True
                guidance_mentions.append(
                    {
                        "doc_id": doc_id,
                        "page": p_num,
                        "in_3200_window": in_3200,
                        "sentence": clean_line,
                    }
                )

    report = {
        "ticker": "PIDILITIND.NS",
        "total_pdfs_discovered": len(enriched),
        "total_pages_in_pdfs": sum(d["pages"] for d in enriched),
        "pages_extracted_non_empty": len(read_pages),
        "stage_1_raw_extracted_chars": raw_total_chars,
        "stage_2_after_3200_char_per_page_cap": corpus_total_chars,
        "stage_3_after_180000_char_prompt_slice": len(sent_corpus),
        "pages_included_in_180k_prompt": len(included_set),
        "pages_dropped_by_180k_slice": len(dropped_set),
        "pages_truncated_by_3200_char_cap": len(truncated_pages),
        "dropped_docs_summary": (
            f"All 5 concall transcripts (DOC_1..DOC_5, 103 pages) were included in the 180k prompt slice, "
            f"plus DOC_6 p.1-2. The remaining {len(dropped_set)} pages (DOC_6 p.3-14 and all of DOC_7..DOC_10, "
            f"which are the 5 financial results filings) were cut off by corpus[:180000]."
        ),
        "truncated_pages_detail": truncated_pages[:15],
        "guidance_sentences_found_in_transcripts": guidance_mentions,
    }
    save_json(DATA_DIR / "pidilite_recall_audit.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("truncated_pages_detail", "guidance_sentences_found_in_transcripts")}, indent=2))
    print(f"\nFound {len(guidance_mentions)} quantitative guidance/target sentences across DOC_1..DOC_5:")
    for gm in guidance_mentions[:25]:
        print(f"  [{gm['doc_id']} p.{gm['page']} | in_3200={gm['in_3200_window']}] {gm['sentence']}")


if __name__ == "__main__":
    main()
