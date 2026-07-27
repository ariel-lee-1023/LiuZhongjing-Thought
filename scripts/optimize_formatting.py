#!/usr/bin/env python3
"""
Optimize formatting of existing Markdown content under content/LZJT/.

Standard LZJ layout recognition:
  ## 内容概要
  ## 金句收集
  ## 正文
  ### <subsection titles under 正文>

CJK spacing fix preserves newlines (critical).
NFKC normalizes compatibility ideographs (⾦→金, ⽂→文).
Never rewrites author words; only layout and heading markers.
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

# Major structural titles → ## 
MAJOR = ["内容概要", "金句收集", "正文"]
MAJOR_SET = set(MAJOR)

# Common subsection titles → ###  (extend as more patterns appear)
SUBSECTION = [
    "对未来社会政治的潜在影响",
    "AI 的信息污染问题",
    "学术定位的改变",
]
SUBSECTION_SET = set(SUBSECTION)

# All titles that force a structural break (longest first for inject)
STRUCTURAL = sorted(MAJOR + SUBSECTION, key=len, reverse=True)

TOC_LINE = re.compile(r"^.{0,50}?\s*[.…·•\-—–]{3,}\s*\d{1,4}\s*$")
GARBAGE_TOC = re.compile(
    r"^(\d{1,4})?#{0,3}\s*(AI\s*的信息污染问题|学术定位的改变|对未来社会政治的潜在影响)?\s*$"
)
EXISTING_HEADING = re.compile(r"^#{1,3}\s+")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fix_cjk_spacing(text: str) -> str:
    """Collapse only horizontal whitespace between CJK — never newlines."""
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


def inject_structural_breaks(text: str) -> str:
    """
    Force known structural titles onto their own lines when glued to body text.
    Order longest-first so longer titles win.
    """
    for title in STRUCTURAL:
        # newline before title if not already at line start
        text = re.sub(rf"(?<!\n)({re.escape(title)})", r"\n\1", text)
        # newline after title when more non-space text follows on same line
        text = re.sub(rf"({re.escape(title)})(?!\n)(?=\S)", r"\1\n", text)
    return text


def reflow_paragraphs(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = inject_structural_breaks(text)
    raw_lines = [ln.rstrip() for ln in text.split("\n")]

    terminal = re.compile(r"[。！？；…」』”’]$")
    force_start = re.compile(
        r"^(问[:：]|答[:：]|内容概要|金句收集|正文|"
        r"第[一二三四五六七八九十百]+[章节讲部]?|"
        r"[（(]?[0-9]{1,2}[)）]|[0-9]+\.|[一二三四五六七八九十]+、|"
        r"[【「].{1,20}[】」])"
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

        # strip existing markdown heading markers so we re-emit cleanly
        if EXISTING_HEADING.match(ln):
            ln = EXISTING_HEADING.sub("", ln).strip()

        if re.fullmatch(r"\d{1,4}", ln) or ln in {"·", "•", "—", "–", "-", "…"}:
            continue
        if GARBAGE_TOC.match(ln) and ln not in MAJOR_SET and ln not in SUBSECTION_SET:
            continue
        if TOC_LINE.match(ln):
            continue

        if not ln:
            if buf and terminal.search(buf[-1]):
                flush()
            continue

        is_structural = (
            ln in MAJOR_SET
            or ln in SUBSECTION_SET
            or force_start.match(ln)
        )
        if buf and (is_structural or terminal.search(buf[-1])):
            flush()

        buf.append(ln)

    flush()

    # mobile length balance
    balanced: list[str] = []
    max_len = 420
    for p in paras:
        if p in MAJOR_SET or p in SUBSECTION_SET or len(p) <= max_len:
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

    # emit with standard hierarchy
    final: list[str] = []
    for p in balanced:
        if p in MAJOR_SET:
            if final and final[-1] != "":
                final.append("")
            final.append(f"## {p}")
            final.append("")
            continue
        if p in SUBSECTION_SET:
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
    # Compatibility ideographs → standard forms (⾦→金, ⽂→文, …)
    text = unicodedata.normalize("NFKC", text)
    text = fix_cjk_spacing(text)
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
