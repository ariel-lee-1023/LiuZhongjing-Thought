#!/usr/bin/env python3
"""
Sync LZJT notes from 得到大脑 topic 40D9VmeJ → Markdown in content/

Auth: repository secrets API (gk_live_...) and CLIENT (cli_...)
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
PAGE_SIZE_HINT = 50  # API may ignore, we still paginate

API_KEY = os.environ.get("API") or os.environ.get("BIJI_API_KEY")
CLIENT_ID = os.environ.get("CLIENT") or os.environ.get("BIJI_CLIENT_ID")

if not API_KEY or not CLIENT_ID:
    print("ERROR: missing API or CLIENT secret", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": API_KEY,  # no Bearer prefix
    "X-Client-ID": CLIENT_ID,
    "Accept": "application/json",
    "User-Agent": "LiuZhongjing-Thought-Sync/1.0",
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
        batch = resp.get("data", {}).get("notes") or resp.get("data", {}).get("list") or []
        if not batch:
            # some responses put notes at top level
            batch = resp.get("notes") or []
        if not batch:
            break
        notes.extend(batch)
        # crude stop: if fewer than expected, done
        if len(batch) < 10:
            break
        page += 1
        if page > 100:  # safety
            break
    print(f"  total notes: {len(notes)}")
    return notes


def get_note_detail(note_id: str) -> dict:
    resp = api_get(
        "/open/api/v1/resource/note/detail",
        {"id": note_id, "image_quality": "original"},
    )
    return resp.get("data", {}).get("note") or resp.get("data") or resp


def safe_filename(title: str, note_id: str) -> str:
    title = title or "untitled"
    # keep CJK + alnum, collapse others
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", title, flags=re.UNICODE)
    cleaned = cleaned.strip("_ ")[:80] or "untitled"
    return f"{note_id}__{cleaned}.md"


def download_file(url: str, dest: Path) -> None:
    # try with auth first, fall back without
    for use_auth in (True, False):
        headers = HEADERS if use_auth else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return
        except requests.HTTPError as e:
            if use_auth:
                continue
            raise e


def convert_pdf(pdf_path: Path) -> str:
    md = MarkItDown()
    result = md.convert(str(pdf_path))
    return result.text_content or ""


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    changed = 0
    md_converter_ok = True

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

        attachments = detail.get("attachments") or []
        pdfs = [a for a in attachments if str(a.get("type", "")).lower() == "pdf" or
                str(a.get("mime_type", "")).lower() == "application/pdf" or
                str(a.get("name", "")).lower().endswith(".pdf")]

        # also surface the note body itself if substantial
        body = (detail.get("content") or "").strip()
        if body and len(body) > 200 and not pdfs:
            # pure text note → write as md
            out_name = safe_filename(title, note_id)
            out_path = CONTENT_DIR / out_name
            header = f"# {title}\n\n> source note_id: `{note_id}`  \n> topic: `{TOPIC_ID}`\n\n"
            full = header + body
            if out_path.exists() and out_path.read_text(encoding="utf-8") == full:
                continue
            out_path.write_text(full, encoding="utf-8")
            print(f"  wrote text note → {out_name}")
            changed += 1
            continue

        for att in pdfs:
            url = att.get("url") or att.get("download_url")
            name = att.get("name") or "document.pdf"
            if not url:
                continue

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
                    md_converter_ok = False
                    continue

                if not md_text.strip():
                    print(f"  empty conversion for {name}")
                    continue

                out_name = safe_filename(title or name, note_id)
                out_path = CONTENT_DIR / out_name
                header = (
                    f"# {title or name}\n\n"
                    f"> source note_id: `{note_id}`  \n"
                    f"> attachment: `{name}`  \n"
                    f"> topic: `{TOPIC_ID}`  \n"
                    f"> converted with markitdown\n\n"
                )
                full = header + md_text

                if out_path.exists():
                    existing = out_path.read_text(encoding="utf-8")
                    if content_hash(existing) == content_hash(full):
                        continue  # unchanged

                out_path.write_text(full, encoding="utf-8")
                print(f"  wrote PDF → {out_name}")
                changed += 1

    print(f"\nDone. {changed} file(s) written/updated.")
    if not md_converter_ok:
        print("WARNING: some conversions failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
