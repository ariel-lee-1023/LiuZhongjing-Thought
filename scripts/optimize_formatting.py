#!/usr/bin/env python3
"""
Optimize formatting of existing Markdown content under content/LZJT/.

Aggressive structural-title injection + CJK reflow + mobile paragraph balancing.
Never rewrites author words; only layout and heading markers.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

CONTENT_ROOT = Path("content") / "LZJT"

SUBFOLDERS = [
    "LZJ-Writings",
    "LZJ-FiguresCritique",
    "LZJ-Lec-HistPhil_MoralPhil_Epist",
]

CJK = r"[\u2e80-\u2eff\u2f00-\u2fdf\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"

# Titles that must become isolated headings
STRUCTURAL = [
    "对未来社会政治的潜在影响",
    "AI 的信息污染问题",
    "学术定位的改变",
    "内容概要",
    "金句收集",
    "正文",
]

SUBSECTION_SET = {
    "AI 的信息污染问题",
    "学术定位的改变",
    "对未来社会政治的潜在影响",
}

MAJOR_SET = {"内容概要", "金句收集", "正文"}

# TOC leader lines (title + dots + page number)
TOC_LINE = re.compile(r"^.{1,40}?\s*[.…·•\-—–]{3,}\s*\d{1,3}$")
# Polluted TOC fragments like "2### AI 的信息污染问题" or bare page numbers
GARBAGE_TOC = re.compile(
    r"^(\d{1,3})?#{0,3}\s*(AI\s*的信息污染问题|学术定位的改变|对未来社会政治的潜在影响)?\s*$"
)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fix_cjk_spacing(text: str) -> str:
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


def inject_structural_breaks(text: str) -> str:
    """
    Force every occurrence of a known structural title onto its own line.
    This is the only reliable way to undo PDF-extractor gluing.
    """
    for title in STRUCTURAL:
        # Always put a newline before the title (unless already at line start)
        text = re.sub(rf"(?<!\n)({re.escape(title)})", r"\n\1", text)
        # Always put a newline after the title when more text follows on the same "line"
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

    i = 0
    while i < len(raw_lines):
        ln = raw_lines[i].strip()

        # Drop pure page numbers and pure decorative dots
        if re.fullmatch(r"\d{1,4}", ln) or ln in {"·", "•", "—", "–", "-", "…"}:
            i += 1
            continue

        # Drop polluted TOC fragments left by earlier broken runs
        if GARBAGE_TOC.match(ln) and not (ln in MAJOR_SET or ln in SUBSECTION_SET):
            i += 1
            continue

        if not ln:
            if buf and terminal.search(buf[-1]):
                flush()
            i += 1
            continue

        is_structural = (
            ln in MAJOR_SET
            or ln in SUBSECTION_SET
            or TOC_LINE.match(ln)
            or force_start.match(ln)
        )
        if buf and (is_structural or terminal.search(buf[-1])):
            flush()

        buf.append(ln)
        i += 1

    flush()

    # Balance overlong paragraphs
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

    # Emit with proper heading isolation; drop pure TOC leader lines
    final: list[str] = []
    for p in balanced:
        if TOC_LINE.match(p):
            # Skip the PDF TOC block — real ## headings replace it
            continue

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
