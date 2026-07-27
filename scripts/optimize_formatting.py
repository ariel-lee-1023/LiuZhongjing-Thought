#!/usr/bin/env python3
"""
Optimize formatting of existing Markdown under content/LZJT/.

Rules:
  - drop PDF TOC (leader dots OR compact page-number TOC like "正文 3xxx 4yyy")
  - drop empty major headings left by prior runs
  - enforce module order: 内容概要 → 金句收集 → 正文
  - unglue only at line-start titles; never invent mid-sentence headings
  - strip stray trailing ## / #
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

MAJOR = ["内容概要", "金句收集", "正文"]  # ordered
MAJOR_SET = set(MAJOR)

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
    "1929 年大萧条的深层原因与问题提出",
    "1929年大萧条的深层原因与问题提出",
    "权力扩张与民主政治的内在逻辑",
    "一战后债务链、关税战与经济危机的延长",
    "德苏易货贸易与走向第二次世界大战",
    "二战后布雷顿森林体系的建立与演化",
    "冷战后美元输出、全球化矛盾与当前体系前景",
}

HAS_LEADER_DOTS = re.compile(r"[.…·•]{4,}")
JUNK = re.compile(r"^(\d{1,4}|[·•—–\-…]{1,8}|#{1,6})$")
PAGE_GLUE = re.compile(r"^\d{1,3}[\u4e00-\u9fff“\"「]")
EXISTING_HEADING = re.compile(r"^#{1,6}\s+")
TRAILING_HASH = re.compile(r"#{1,6}\s*$")
COMPACT_TOC = re.compile(r"^正文\s*\d")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


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
    titles = sorted(MAJOR_SET | SUBSECTION, key=len, reverse=True)
    for title in titles:
        text = re.sub(
            rf"(^|\n)({re.escape(title)})(?=[\u4e00-\u9fff“\"「『答问])",
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
    if COMPACT_TOC.match(ln):
        return True
    nums = re.findall(r"(?<!\d)\d{1,3}(?!\d)", ln)
    if len(nums) >= 4 and len(ln) < 500:
        return True
    return False


def strip_toc_block_after_summary_title(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        bare = EXISTING_HEADING.sub("", ln).strip()
        bare = TRAILING_HASH.sub("", bare).strip()
        out.append(ln)
        if bare == "内容概要":
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                nxt_bare = EXISTING_HEADING.sub("", nxt).strip()
                nxt_bare = TRAILING_HASH.sub("", nxt_bare).strip()
                if not nxt_bare:
                    i += 1
                    continue
                if nxt_bare.startswith(("本次", "本讲", "本节", "本文", "本篇", "本分享")):
                    break
                if (
                    len(nxt_bare) > 80
                    and nxt_bare.endswith("。")
                    and not is_toc_line(nxt_bare)
                ):
                    break
                if nxt_bare in MAJOR_SET or nxt_bare in SUBSECTION:
                    break
                if EXISTING_HEADING.match(nxt) and nxt_bare in MAJOR_SET:
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
        s = ln.strip()
        s = TRAILING_HASH.sub("", s).strip()
        if is_toc_line(s):
            continue
        if TRAILING_HASH.search(ln.strip()):
            filtered.append(TRAILING_HASH.sub("", ln.strip()).rstrip())
        else:
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
        p = TRAILING_HASH.sub("", p).strip()
        if p:
            paras.append(p)
        buf.clear()

    for ln in filtered:
        ln = ln.strip()
        if EXISTING_HEADING.match(ln):
            ln = EXISTING_HEADING.sub("", ln).strip()
        ln = TRAILING_HASH.sub("", ln).strip()
        if not ln:
            if buf and terminal.search(buf[-1]):
                flush()
            continue
        if is_toc_line(ln):
            continue

        is_exact_title = ln in MAJOR_SET or ln in SUBSECTION
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
        if p in MAJOR_SET or p in SUBSECTION or len(p) <= max_len:
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

    # collect under each major; drop empties; emit fixed order
    sections: dict[str, list[str]] = {m: [] for m in MAJOR}
    current: str | None = None
    preamble: list[str] = []
    extras: list[str] = []

    for p in balanced:
        if p in MAJOR_SET:
            current = p
            continue
        if current is None:
            preamble.append(p)
            continue
        if current == "正文":
            if p in SUBSECTION:
                extras.append(f"### {p}")
            else:
                extras.append(p)
        else:
            sections[current].append(p)

    final: list[str] = []
    for p in preamble:
        if p in MAJOR_SET:
            continue
        final.append(p)

    for m in MAJOR:
        body = sections[m]
        if not body and m != "正文":
            continue
        if m == "正文" and not body and not extras:
            continue
        if final and final[-1] != "":
            final.append("")
        final.append(f"## {m}")
        final.append("")
        for b in body:
            final.append(b)
        if m == "正文":
            for e in extras:
                final.append(e)

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


def split_header_body(full: str) -> tuple[str, str]:
    lines = full.splitlines(keepends=True)
    if not lines:
        return "", full
    header_end = 0
    in_meta = False
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped.startswith("#") and not stripped.startswith("## "):
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
