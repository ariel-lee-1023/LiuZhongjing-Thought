#!/usr/bin/env python3
"""
Sync ONLY PDFs that belong to the LZJT hierarchy from 得到大脑 topic 40D9VmeJ.

Rules (strict):
- Only process notes that have PDF attachments.
- Only keep notes that are under the LZJT folder tree
  (title / topics / path contains LZJT or known sub-folders).
- Preserve classification by writing into content/LZJT/<subfolder>/...
- Never write pure text notes, audio, or anything outside LZJT.

Auth: repository secrets API + CLIENT
Conversion: microsoft/markitdown[pdf]
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests
from markitdown import MarkItDown

BASE_URL = "https://openapi.biji.com"
TOPIC_ID = "40D9VmeJ"
CONTENT_DIR = Path("content")

# Known LZJT sub-folders from the UI (used for path reconstruction)
LZJT_SUBFOLDERS = {
    "LZJ-Writings",
    "LZJ-FiguresCritique",
    "LZJ-Lec-HistPhil_MoralPhil_Epist",
    "LZJT",
}

API_KEY = os.environ.get("API") or os.environ.get("BIJI_API_KEY")
CLIENT_ID = os.environ.get("CLIENT") or os.environ.get("BIJI_CLIENT_ID")

if not API_KEY or not CLIENT_ID:
    print("ERROR: missing API or CLIENT secret", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": API_KEY,  # no Bearer prefix
    "X-Client-ID": CLIENT_ID,
    "Accept": "application/json",
    "User-Agent": "LiuZhongjing-Thought-Sync/1.1",
}


def api_get(path: str, params: dict[str, Any] | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    r = requests.get(url, headers=HEADERS, params=params or {}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not data.get("success", True):
        raise RuntimeError(f"API error: {data}")
    return data


def list_all_notes() -> list[dict]:
    notes: list[dict] = []
    page = 1
    while True:
        print(f"  listing notes page {page}...")
        resp = api_get(
            "/open/api/v1/resource/knowledge/notes",
            {"topic_id": TOPIC_ID, "page": page},
        )
        data = resp.get("data") or {}
        batch = data.get("notes") or data.get("list") or resp.get("notes") or []
        if not batch:
            break
        notes.extend(batch)
        print(f"    got {len(batch)} notes")
        if len(batch) < 5:
            break
        page += 1
        if page > 200:
            break
    print(f"  total notes returned by API: {len(notes)}")
    return notes


def get_note_detail(note_id: str) -> dict:
    resp = api_get(
        "/open/api/v1/resource/note/detail",
        {"id": note_id, "image_quality": "original"},
    )
    return resp.get("data", {}).get("note") or resp.get("data") or resp


def is_under_lzjt(detail: dict, title: str) -> bool:
    """Heuristic: only keep notes that belong to the LZJT tree."""
    title_l = (title or "").lower()
    if "lzjt" in title_l or "lzj-" in title_l or "刘仲敬" in title or "阿姨" in title:
        return True

    # check topics array
    for t in detail.get("topics") or []:
        name = str(t.get("name") or t.get("topic_name") or "").lower()
        if "lzjt" in name or "刘仲敬" in name:
            return True

    # check tags
    for tag in detail.get("tags") or []:
        name = str(tag.get("name") if isinstance(tag, dict) else tag).lower()
        if "lzjt" in name or "lzj" in name:
            return True

    return False


def guess_subfolder(detail: dict, title: str) -> str:
    """Try to map to one of the known UI sub-folders."""
    candidates = [title or ""]
    for t in detail.get("topics") or []:
        candidates.append(str(t.get("name") or ""))
    for tag in detail.get("tags") or []:
        candidates.append(str(tag.get("name") if isinstance(tag, dict) else tag))

    text = " ".join(candidates)
    for folder in LZJT_SUBFOLDERS:
        if folder.lower() in text.lower():
            return folder
    # fallback
    return "LZJT"


def safe_name(name: str) -> str:
    name = name or "untitled"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def download_file(url: str, dest: Path) -> None:
    for use_auth in (True, False):
        headers = HEADERS if use_auth else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return
        except requests.HTTPError:
            if use_auth:
                continue
            raise


def convert_pdf(pdf_path: Path) -> str:
    md = MarkItDown()
    result = md.convert(str(pdf_path))
    return result.text_content or ""


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    changed = 0
    pdf_count = 0
    skipped_non_lzjt = 0
    skipped_no_pdf = 0

    try:
        notes = list_all_notes()
    except Exception as e:
        print(f"FATAL listing notes: {e}", file=sys.stderr)
        return 1

    for n in notes:
        note_id = str(n.get("note_id") or n.get("id") or "")
        title = n.get("title") or n.get("name") or ""
        if not note_id:
            continue

        try:
            detail = get_note_detail(note_id)
        except Exception as e:
            print(f"  skip {note_id}: detail failed ({e})")
            continue

        # 1. must be under LZJT
        if not is_under_lzjt(detail, title):
            skipped_non_lzjt += 1
            continue

        # 2. only PDFs
        attachments = detail.get("attachments") or []
        pdfs = [
            a for a in attachments
            if str(a.get("type", "")).lower() == "pdf"
            or str(a.get("mime_type", "")).lower() == "application/pdf"
            or str(a.get("name", "")).lower().endswith(".pdf")
        ]

        if not pdfs:
            skipped_no_pdf += 1
            continue

        subfolder = guess_subfolder(detail, title)
        out_dir = CONTENT_DIR / "LZJT" / subfolder
        out_dir.mkdir(parents=True, exist_ok=True)

        for att in pdfs:
            url = att.get("url") or att.get("download_url")
            name = att.get("name") or "document.pdf"
            if not url:
                continue

            pdf_count += 1
            with tempfile.TemporaryDirectory() as tmp:
                pdf_path = Path(tmp) / name
                try:
                    download_file(url, pdf_path)
                except Exception as e:
                    print(f"  download failed {name}: {e}")
                    continue

                try:
                    md_text = convert_pdf(pdf_path)
                except Exception as e:
                    print(f"  convert failed {name}: {e}")
                    continue

                if not md_text.strip():
                    print(f"  empty conversion for {name}")
                    continue

                base = safe_name(Path(name).stem or title or note_id)
                out_path = out_dir / f"{base}.md"

                header = (
                    f"# {title or base}\n\n"
                    f"> source note_id: `{note_id}`  \n"
                    f"> original PDF: `{name}`  \n"
                    f"> folder: `LZJT/{subfolder}`  \n"
                    f"> topic: `{TOPIC_ID}`  \n"
                    f"> converted with markitdown\n\n"
                )
                full = header + md_text

                if out_path.exists():
                    existing = out_path.read_text(encoding="utf-8")
                    if content_hash(existing) == content_hash(full):
                        continue

                out_path.write_text(full, encoding="utf-8")
                print(f"  wrote PDF → LZJT/{subfolder}/{out_path.name}")
                changed += 1

    print(f"\nDone.")
    print(f"  PDFs processed : {pdf_count}")
    print(f"  files written  : {changed}")
    print(f"  skipped (not LZJT): {skipped_non_lzjt}")
    print(f"  skipped (no PDF)  : {skipped_no_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
