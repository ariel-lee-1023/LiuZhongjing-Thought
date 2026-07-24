# LiuZhongjing-Thought

Automated archive of **刘仲敬思想 (LZJT)** materials from the 得到大脑 (biji.com) knowledge base topic [`40D9VmeJ`](https://biji.com/topic/40D9VmeJ).

## What this does

1. Uses the 得到大脑 OpenAPI (with repository secrets `API` + `CLIENT`) to list every note in the topic.
2. For each note that carries PDF attachments, downloads the PDF.
3. Converts the PDF → clean Markdown with [Microsoft MarkItDown](https://github.com/microsoft/markitdown).
4. Commits the resulting `.md` files into this repository under `content/`.
5. Runs on a schedule (and can be triggered manually) so the archive stays up-to-date.

## Secrets required (already set)

| Secret name | Value |
|-------------|-------|
| `API`       | `gk_live_...` (得到大脑 API Key) |
| `CLIENT`    | `cli_...` (X-Client-ID) |

## Manual trigger

Go to **Actions → Sync LZJT from 得到大脑 → Run workflow**.

## Layout

```
content/
  ├── <note-id>__<safe-title>.md   # converted from PDF attachment
  └── ...
.github/workflows/sync-lzjt.yml
scripts/sync_from_biji.py
```

## Conversion quality note

MarkItDown’s PDF path is text-extraction based (pdfminer). Layout-heavy academic PDFs may need light post-editing. That is expected and acceptable for an automated archive.

---
Real-Engineer style: small, reliable, no magic.
