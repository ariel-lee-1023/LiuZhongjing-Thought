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

Extraction: PyMuPDF (fitz) — continuous CJK text, no hallucinated tables.
Post-process:
  1. Aggressive CJK inter-character space cleanup
  2. Soft page-break handling (join mid-sentence across pages)
  3. Intelligent paragraph reflow for Chinese prose + length balancing
  4. Force new paragraphs on 问：/答： and section headers
  5. Light heading detection (short lines ending ：) → **bold** isolation
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
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_text(pdf_path: Path) -> str:
    """Extract raw text with PyMuPDF. Prefer continuous text over layout reconstruction."""
    doc = fitz.open(pdf_path)
    parts: list[str] = []
    for page in doc:
        t = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_DEHYPHENATE)
        parts.append(t)
    doc.close()
    return "\n".join(parts)


def fix_cjk_spacing(text: str) -> str:
    """Remove spurious spaces that pdf extractors insert between CJK glyphs."""
    text = re.sub(rf"({CJK})\s+(?={CJK})", r"\1", text)

    punct = r"[，。！？；：、“”‘’（）【】《》〈〉「」『』、]"
    text = re.sub(rf"({CJK})\s+({punct})", r"\1\2", text)
    text = re.sub(rf"({punct})\s+({CJK})", r"\1\2", text)

    text = re.sub(rf"([（【《〈「『“‘])\s+", r"\1", text)
    text = re.sub(rf"\s+([）】》〉」』”’])", r"\1", text)

    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    text = re.sub(r"(?<=\d)\s*[~～—–-]\s*(?=\d)", "~", text)

    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def reflow_paragraphs(text: str) -> str:
    """
    Rejoin visual lines into readable Chinese paragraphs, then balance length.

    Key behaviours:
    - Soft blanks (page breaks / layout gaps) do NOT force a paragraph break
      unless the previous line already ends with sentence-terminal punctuation.
    - Pure page numbers are dropped silently and never force a break.
    - Lines starting with 问：/答： or common section markers force a new paragraph.
    - Consecutive non-terminal lines are concatenated (no space for pure CJK).
    - Overlong paragraphs are split only at sentence ends for mobile rhythm.
    - Short heading-like lines (ending ：) receive **bold** + blank isolation.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    raw_lines = [ln.rstrip() for ln in text.split("\n")]

    terminal = re.compile(r"[。！？；…」』”’]$")
    force_start = re.compile(
        r"^(问[:：]|答[:：]|内容概要|金句收集|正文|"
        r"第[一二三四五六七八九十百]+[章节讲部]?|"
        r"[（(]?[0-9]{1,2}[)）]|[0-9]+\.|[一二三四五六七八九十]+、|"
        r"[【「].{1,20}[】」])"
    )
    heading_like = re.compile(
        r"^.{1,40}[:：]$|^[【「].{1,30}[】」]$"
    )

    paras: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        p = "".join(buf)
        p = re.sub(r" {2,}", " ", p).strip()
        if p:
            paras.append(p)
        buf.clear()

    i = 0
    while i < len(raw_lines):
        ln = raw_lines[i].strip()

        # Silent skip — page numbers & pure noise never break paragraphs
        if re.fullmatch(r"\d{1,4}", ln) or ln in {"·", "•", "—", "–", "-", "…"}:
            i += 1
            continue

        if not ln:
            # Soft blank: only hard-break when the current sentence is already finished
            if buf and terminal.search(buf[-1]):
                flush()
            i += 1
            continue

        # Hard break conditions
        if buf and (force_start.match(ln) or terminal.search(buf[-1]) or heading_like.match(ln)):
            flush()

        buf.append(ln)
        i += 1

    flush()

    # Balance overlong paragraphs for mobile reading rhythm
    balanced: list[str] = []
    max_len = 420
    for p in paras:
        if len(p) <= max_len:
            balanced.append(p)
            continue
        parts = re.split(r"(?<=[。！？；…])", p)
        current = ""
        for part in parts:
            if not part.strip():
                continue
            if current and len(current) + len(part) > max_len:
                balanced.append(current.strip())
                current = part
            else:
                current += part
        if current.strip():
            balanced.append(current.strip())

    # Light heading formatting
    final: list[str] = []
    for p in balanced:
        if heading_like.match(p) and len(p) < 45:
            final.append("")
            final.append(f"**{p}**")
            final.append("")
        else:
            final.append(p)

    text = "\n\n".join(x for x in final if x is not None)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_layout(text: str) -> str:
    """Full pipeline: CJK space fix → intelligent reflow + balance."""
    text = fix_cjk_spacing(text)
    text = reflow_paragraphs(text)
    # Final safety collapse of any residual excessive blanks
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
        f"> converted with PyMuPDF + CJK reflow + mobile balance\n\n"
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
