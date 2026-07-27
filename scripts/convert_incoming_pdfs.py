#!/usr/bin/env python3
"""
Convert PDFs dropped into incoming/ into clean Markdown under content/LZJT/

Same design as optimize_formatting.py:
  - drop PDF TOC entirely (leader dots + block after 内容概要)
  - arrange by real structure, never invent mid-sentence titles
  - unglue only at line-start title+body artifacts
"""

from __future__ import annotations

import hashlib
import re
import sys
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

INCOMING_ROOT = Path("incoming")
CONTENT_ROOT = Path("content") / "LZJT"

SUBFOLDERS = [
    "LZJ-Writings",
    "LZJ-FiguresCritique",
    "LZJ-Lec-HistPhil_MoralPhil_Epist",
]

CJK = r"[\u2e80-\u2eff\u2f00-\u2fdf\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"

MAJOR = {"内容概要", "金句收集", "正文"}
SUBSECTION = {
    "对未来社会政治的潜在影响",
    "AI 的信息污染问题",
    "学术定位的改变",
    "世界文明起源与早期传播路径",
    "殷商时期的方国概念与夏、诸夏概念的产生",
    "秦汉到明清时期的认同演变",
    "晚清到民国的国家认同建构过程",
    "国民党北伐后政治路径的形成",
    "答问环节",
}

HAS_LEADER_DOTS = re.compile(r"[.…·•]{4,}")
JUNK = re.compile(r"^(\d{1,4}|[·•—–\-…]{1,8})$")
PAGE_GLUE = re.compile(r"^\d{1,3}[\u4e00-\u9fff“\"「]")
EXISTING_HEADING = re.compile(r"^#{1,6}\s+")


def safe_name(name: str) -> str:
    name = name or "untitled"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    parts: list[str] = []
    for page in doc:
        t = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_DEHYPHENATE)
        parts.append(t)
    doc.close()
    return "\n".join(parts)


def fix_cjk_spacing(text: str) -> str:
    text = re.sub(rf"({CJK})[ \t]+(?={CJK})", r"\1", text)
    punct = r"[，。！？；：、“”‘’（）【】《》〈〉「」『』、]"
    text = re.sub(rf"({CJK})[ \t]+({punct})", r"\1\2", text)
    text = re.sub(rf"({punct})[ \t]+({CJK})", r"\1\2", text)
    text = re.sub(rf"([（【《〈「『“‘])[ \t]+", r"\1", text)
    text = re.sub(rf"[ \t]+([）】》〉」』”’])", r"\1", text)
    text = re.sub(r"(?<=\d)[ \t]+(?=\d)", "", text)
    text = re.sub(r"(?<=\d)[ \t]*[~～—–-][ \t]*(?=\d)", "~", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def unglue_leading_titles(text: str) -> str:
    titles = sorted(MAJOR | SUBSECTION, key=len, reverse=True)
    for title in titles:
        text = re.sub(
            rf"(^|\n)({re.escape(title)})(?=[\u4e00-\u9fff“\"「『])",
            r"\1\2\n",
            text,
        )
    return text


def is_toc_line(ln: str) -> bool:
    if not ln:
        return False
    if JUNK.match(ln):
        return True
    if HAS_LEADER_DOTS.search(ln):
        return True
    if PAGE_GLUE.match(ln):
        return True
    return False


def strip_toc_block_after_summary_title(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        bare = EXISTING_HEADING.sub("", ln).strip()
        out.append(ln)
        if bare == "内容概要":
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                nxt_bare = EXISTING_HEADING.sub("", nxt).strip()
                if not nxt_bare:
                    i += 1
                    continue
                if nxt_bare.startswith(("本次", "本讲", "本节", "本文", "本篇")):
                    break
                if (
                    len(nxt_bare) > 80
                    and nxt_bare.endswith("。")
                    and not HAS_LEADER_DOTS.search(nxt_bare)
                    and not is_toc_line(nxt_bare)
                ):
                    break
                if nxt_bare in MAJOR or nxt_bare in SUBSECTION:
                    break
                if EXISTING_HEADING.match(nxt) and nxt_bare in MAJOR:
                    break
                i += 1
            continue
        i += 1
    return out


def reflow_paragraphs(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    raw_lines = [ln.rstrip() for ln in text.split("\n")]

    filtered: list[str] = []
    for ln in raw_lines:
        if is_toc_line(ln.strip()):
            continue
        filtered.append(ln)
    filtered = strip_toc_block_after_summary_title(filtered)

    terminal = re.compile(r"[。！？；…」』”’]$")
    force_start = re.compile(
        r"^(问[:：]|答[:：]|提问[一二三四五六七八九十]+[:：]?|"
        r"第[一二三四五六七八九十百]+[章节讲部]?|"
        r"[（(]?[0-9]{1,2}[)）]|[0-9]+\.|[一二三四五六七八九十]+、)"
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

    for ln in filtered:
        ln = ln.strip()
        if EXISTING_HEADING.match(ln):
            ln = EXISTING_HEADING.sub("", ln).strip()
        if not ln:
            if buf and terminal.search(buf[-1]):
                flush()
            continue
        if is_toc_line(ln):
            continue
        is_exact_title = ln in MAJOR or ln in SUBSECTION
        is_force = bool(force_start.match(ln))
        if buf and (is_exact_title or is_force or terminal.search(buf[-1])):
            flush()
        if is_exact_title:
            paras.append(ln)
            continue
        buf.append(ln)
    flush()

    balanced: list[str] = []
    max_len = 420
    for p in paras:
        if p in MAJOR or p in SUBSECTION or len(p) <= max_len:
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

    final: list[str] = []
    last_major: str | None = None
    for p in balanced:
        if p in MAJOR:
            if p == last_major:
                continue
            if final and final[-1] != "":
                final.append("")
            final.append(f"## {p}")
            final.append("")
            last_major = p
            continue
        last_major = None
        if p in SUBSECTION:
            if final and final[-1] != "":
                final.append("")
            final.append(f"### {p}")
            final.append("")
            continue
        final.append(p)

    text = "\n\n".join(x for x in final if x is not None)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_layout(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = fix_cjk_spacing(text)
    text = unglue_leading_titles(text)
    text = unglue_leading_titles(text)
    text = reflow_paragraphs(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def convert_one(pdf_path: Path, out_dir: Path) -> bool:
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
        f"> converted with PyMuPDF + CJK reflow + structural headings\n\n"
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
