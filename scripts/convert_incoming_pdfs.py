#!/usr/bin/env python3
"""
Convert PDFs dropped into incoming/ into Markdown under content/LZJT/

Directory mapping (strict):
  incoming/LZJ-Writings/*.pdf
      → content/LZJT/LZJ-Writings/<name>.md
  incoming/LZJ-FiguresCritique/*.pdf
      → content/LZJT/LZJ-FiguresCritique/<name>.md
  incoming/LZJ-Lec-HistPhil_MoralPhil_Epist/*.pdf
      → content/LZJT/LZJ-Lec-HistPhil_MoralPhil_Epist/<name>.md

After successful conversion the source PDF is deleted (keeps the repo light).
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

from markitdown import MarkItDown

INCOMING_ROOT = Path("incoming")
CONTENT_ROOT = Path("content") / "LZJT"

SUBFOLDERS = [
    "LZJ-Writings",
    "LZJ-FiguresCritique",
    "LZJ-Lec-HistPhil_MoralPhil_Epist",
]


def safe_name(name: str) -> str:
    name = name or "untitled"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def convert_one(pdf_path: Path, out_dir: Path) -> bool:
    """Convert a single PDF. Returns True if a new/changed .md was written."""
    md = MarkItDown()
    try:
        result = md.convert(str(pdf_path))
        text = (result.text_content or "").strip()
    except Exception as e:
        print(f"  CONVERT FAIL {pdf_path.name}: {e}")
        return False

    if not text:
        print(f"  EMPTY      {pdf_path.name}")
        return False

    base = safe_name(pdf_path.stem)
    out_path = out_dir / f"{base}.md"

    header = (
        f"# {pdf_path.stem}\n\n"
        f"> original PDF: `{pdf_path.name}`  \n"
        f"> folder: `LZJT/{out_dir.name}`  \n"
        f"> converted with markitdown\n\n"
    )
    full = header + text

    if out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        if content_hash(existing) == content_hash(full):
            print(f"  SKIP (unchanged) {out_path.relative_to(CONTENT_ROOT.parent)}")
            # still delete the PDF so it doesn't stay forever
            pdf_path.unlink(missing_ok=True)
            return False

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full, encoding="utf-8")
    print(f"  WROTE     {out_path.relative_to(CONTENT_ROOT.parent)}")

    # remove source PDF after success
    pdf_path.unlink(missing_ok=True)
    print(f"  DELETED   {pdf_path}")
    return True


def main() -> int:
    changed = 0
    total_pdfs = 0

    for sub in SUBFOLDERS:
        src_dir = INCOMING_ROOT / sub
        if not src_dir.is_dir():
            print(f"(no folder) {src_dir}")
            continue

        pdfs = sorted(src_dir.glob("*.pdf")) + sorted(src_dir.glob("*.PDF"))
        if not pdfs:
            print(f"(empty)    {src_dir}")
            continue

        print(f"\n=== {sub} ({len(pdfs)} PDF(s)) ===")
        out_dir = CONTENT_ROOT / sub

        for pdf in pdfs:
            total_pdfs += 1
            if convert_one(pdf, out_dir):
                changed += 1

    print(f"\nDone. scanned={total_pdfs}  written/updated={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
