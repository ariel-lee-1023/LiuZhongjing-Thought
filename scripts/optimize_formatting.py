#!/usr/bin/env python3
"""
Optimize formatting of existing Markdown under content/LZJT/.

Design (correct arrangement, not invented titles):
  1. NFKC + CJK spacing that NEVER collapses newlines
  2. Drop PDF TOC leader lines (dots + page numbers)
  3. Reflow: join mid-sentence soft breaks; hard-break only on terminal punct
  4. Promote a line to ## / ### ONLY when it is already an exact standalone
     short line matching a known section marker — never inject mid-sentence
  5. Unglue only when a known title sits at line START glued to following body
  6. Never rewrite author words
"""

from __future__ import annotations

import hashlib
import re
import sys
import unicodedata
from pathlib import Path

CONTENT_ROOT = Path("content") / "LZJT"

SUBFOLDERS = [
    "LZJ-Writings",
    "LZJ-FiguresCritique",
    "LZJ-Lec-HistPhil_MoralPhil_Epist",
]

CJK = r"[\u2e80-\u2eff\u2f00-\u2fdf\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"

# Only promote when a line is EXACTLY this (after strip) — never mid-sentence inject
MAJOR = {"内容概要", "金句收集", "正文"}
# Subsections only when exact standalone line
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

# TOC: title + leader dots/ellipsis + page number
TOC_LINE = re.compile(
    r"^.{0,80}?\s*[.…·•\-—–\.]{4,}\s*\d{1,4}\s*$"
)
# Pure page number or pure decorative
JUNK = re.compile(r"^(\d{1,4}|[·•—–\-…]{1,8})$")
EXISTING_HEADING = re.compile(r"^#{1,6}\s+")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fix_cjk_spacing(text: str) -> str:
    """Only horizontal whitespace between CJK — never newlines."""
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
    """
    Only split when a known title sits at the START of a line and is glued
    directly to following body (PDF-extractor artifact). Never touches
    mid-sentence occurrences.
    """
    titles = sorted(MAJOR | SUBSECTION, key=len, reverse=True)
    for title in titles:
        # line-start (or start of string) + title + immediate CJK/quote
        text = re.sub(
            rf"(^|\n)({re.escape(title)})(?=[\u4e00-\u9fff“\"「『])",
            r"\1\2\n",
            text,
        )
    return text


def reflow_paragraphs(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    raw_lines = [ln.rstrip() for ln in text.split("\n")]

    terminal = re.compile(r"[。！？；…」』”’]$")
    # Force new para only for dialogue markers / numbered items at line start
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

    for ln in raw_lines:
        ln = ln.strip()

        # strip existing markdown heading markers; re-emit cleanly later
        if EXISTING_HEADING.match(ln):
            ln = EXISTING_HEADING.sub("", ln).strip()

        if not ln:
            if buf and terminal.search(buf[-1]):
                flush()
            continue

        if JUNK.match(ln) or TOC_LINE.match(ln):
            continue

        # Exact known title on its own line → structural break
        is_exact_title = ln in MAJOR or ln in SUBSECTION
        is_force = bool(force_start.match(ln))

        if buf and (is_exact_title or is_force or terminal.search(buf[-1])):
            flush()

        # If exact title, emit as its own para immediately
        if is_exact_title:
            paras.append(ln)
            continue

        buf.append(ln)

    flush()

    # mobile length balance (~420 CJK chars), only at sentence boundaries
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

    # Emit: only exact standalone titles get ## / ###
    final: list[str] = []
    for p in balanced:
        if p in MAJOR:
            if final and final[-1] != "":
                final.append("")
            final.append(f"## {p}")
            final.append("")
            continue
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
    text = unglue_leading_titles(text)  # second pass for newly split line starts
    text = reflow_paragraphs(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_header_body(full: str) -> tuple[str, str]:
    lines = full.splitlines(keepends=True)
    if not lines:
        return "", full

    header_end = 0
    in_meta = False
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped.startswith("#"):
            header_end = i + 1
            continue
        if stripped.startswith(">"):
            in_meta = True
            header_end = i + 1
            continue
        if in_meta and not stripped:
            header_end = i + 1
            continue
        if in_meta and stripped:
            break
        if not stripped:
            header_end = i + 1
            continue
        break

    header = "".join(lines[:header_end]).rstrip() + "\n\n"
    body = "".join(lines[header_end:]).strip()
    return header, body


def optimize_one(md_path: Path) -> bool:
    try:
        original = md_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  READ FAIL {md_path}: {e}")
        return False

    header, body = split_header_body(original)
    if not body or len(body) < 20:
        return False

    cleaned_body = clean_layout(body)
    new_full = header + cleaned_body + "\n"

    if content_hash(original) == content_hash(new_full):
        return False

    md_path.write_text(new_full, encoding="utf-8")
    print(f"  OPTIMIZED {md_path.relative_to(CONTENT_ROOT.parent)}")
    return True


def main() -> int:
    changed = 0
    total = 0

    for sub in SUBFOLDERS:
        src_dir = CONTENT_ROOT / sub
        if not src_dir.is_dir():
            print(f"(no folder) {src_dir}")
            continue

        mds = sorted(src_dir.glob("*.md"))
        if not mds:
            print(f"(empty)    {src_dir}")
            continue

        print(f"\n=== {sub} ({len(mds)} file(s)) ===")
        for md in mds:
            total += 1
            if optimize_one(md):
                changed += 1

    print(f"\nDone. scanned={total}  optimized={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
