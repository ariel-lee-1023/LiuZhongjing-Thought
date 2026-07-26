#!/usr/bin/env python3
"""
Convert PDFs dropped into incoming/ into clean Markdown under content/LZJT/

Directory mapping (strict):
  incoming/LZJ-Writings/*.pdf
      → content/LZJT/LZJ-Writings/<name>.md
  incoming/LZJ-FiguresCritique/*.pdf
      → content/LZJT/LZJ-FiguresCritique/<name>.md
  incoming/LZJ-Lec-HistPhil_MoralPhil_Epist/*.pdf
      → content/LZJT/LZJ-Lec-HistPhil_MoralPhil_Epist/<name>.md

After successful conversion the source PDF is deleted (keeps the repo light).

Extraction: PyMuPDF (fitz) — better CJK continuity, no hallucinated tables.
Post-process: aggressive CJK space cleanup, page-number / form-feed removal,
paragraph normalization. Designed for continuous Chinese prose essays.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

INCOMING_ROOT = Path("incoming")
CONTENT_ROOT = Path("content") / "LZJT"

SUBFOLDERS = [
    "LZJ-Writings",
    "LZJ-FiguresCritique",
    "LZJ-Lec-HistPhil_MoralPhil_Epist",
]

# Broad CJK + full-width + compatibility ideographs + Kangxi radicals
CJK = r"[\u2e80-\u2eff\u2f00-\u2fdf\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"


def safe_name(name: str) -> str:
    name = name or "untitled"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+\", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_text(pdf_path: Path) -> str:
    """Extract raw text with PyMuPDF. Prefer continuous text over layout reconstruction."""
    doc = fitz.open(pdf_path)
    parts: list[str] = []
    for page in doc:
        # "text" mode gives reading-order text; flags suppress some artifacts
        t = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_DEHYPHENATE)
        parts.append(t)
    doc.close()
    return "\n".join(parts)


def fix_cjk_spacing(text: str) -> str:
    """Remove spurious spaces that pdf extractors insert between CJK glyphs."""
    # Core: CJK + spaces + CJK → CJKCJK
    text = re.sub(rf"({CJK})\s+(?={CJK})", r"\1", text)

    # CJK + spaces + CJK punctuation → stick
    punct = r"[，。！？；：、“”‘’（）【】《》〈〉「」『』、]"
    text = re.sub(rf"({CJK})\s+({punct})", r"\1\2", text)
    text = re.sub(rf"({punct})\s+({CJK})", r"\1\2", text)

    # Opening / closing brackets & quotes: remove adjacent spaces
    text = re.sub(rf"([（【《〈「『“‘])\s+", r"\1", text)
    text = re.sub(rf"\s+([）】》〉」』”’])", r"\1", text)

    # Digit sequences that were spaced out (e.g. 1 7 8 5 → 1785)
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)

    # Year ranges 1785 ~ 1850 → 1785~1850
    text = re.sub(r"(?<=\d)\s*[~～—–-]\s*(?=\d)", "~", text)

    # Collapse residual runs of spaces (keep single space for mixed CJK/Latin)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def clean_layout(text: str) -> str:
    """Normalize page breaks, isolated page numbers, and excessive blank lines."""
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Form-feed / page break markers
    text = text.replace("\f", "\n")

    lines = text.split("\n")
    cleaned: list[str] = []
    for line in lines:
        s = line.strip()
        # Drop pure page-number lines (common in these scans/exports)
        if re.fullmatch(r"\d{1,4}", s):
            continue
        # Drop very short noise lines that are just punctuation or symbols
        if s in {"", "·", "•", "—", "–", "-", "…"}:
            cleaned.append("")  # keep as blank for paragraph
            continue
        cleaned.append(line.rstrip())

    text = "\n".join(cleaned)

    # Apply CJK fix after line-level cleanup
    text = fix_cjk_spacing(text)

    # Strip trailing spaces per line again
    text = "\n".join(ln.rstrip() for ln in text.split("\n"))

    # Collapse 3+ blank lines → 2 (paragraph separator)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def convert_one(pdf_path: Path, out_dir: Path) -> bool:
    """Convert a single PDF. Returns True if a new/changed .md was written."""
    try:
        raw = extract_text(pdf_path)
        text = clean_layout(raw)
    except Exception as e:
        print(f"  CONVERT FAIL {pdf_path.name}: {e}")
        return False

    if not text or len(text) < 20:
        print(f"  EMPTY RESULT {pdf_path.name}")
        return False

    base = safe_name(pdf_path.stem)
    out_path = out_dir / f"{base}.md"

    header = (
        f"# {pdf_path.stem}\n\n"
        f"> original PDF: `{pdf_path.name}`  \n"
        f"> folder: `LZJT/{out_dir.name}`  \n"
        f"> converted with PyMuPDF + CJK layout cleanup\n\n"
    )
    full = header + text

    if out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        if content_hash(existing) == content_hash(full):
            print(f"  SKIP (unchanged) {out_path.relative_to(CONTENT_ROOT.parent)}")
            pdf_path.unlink(missing_ok=True)
            return False

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full, encoding="utf-8")
    print(f"  WROTE     {out_path.relative_to(CONTENT_ROOT.parent)}")

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
