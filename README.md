# LiuZhongjing-Thought

Automated archive of **刘仲敬思想 (LZJT)** **PDF** materials only.

Source: 得到大脑 knowledge base topic [`40D9VmeJ`](https://biji.com/topic/40D9VmeJ) → folder **LZJT** and its sub-folders.

## Strict rules

- **Only PDFs** that live under the LZJT hierarchy are converted.
- Converted with [Microsoft MarkItDown](https://github.com/microsoft/markitdown).
- Output preserves the original classification:

```
content/
└── LZJT/
    ├── LZJ-Writings/
    ├── LZJ-FiguresCritique/
    ├── LZJ-Lec-HistPhil_MoralPhil_Epist/
    └── ...
```

- Pure text notes, audio, and anything outside LZJT are **never** uploaded.

## Secrets (already set)

| Secret  | Value                          |
|---------|--------------------------------|
| `API`   | `gk_live_...` (得到大脑 API Key) |
| `CLIENT`| `cli_...` (X-Client-ID)        |

## How to run

**Actions → Sync LZJT from 得到大脑 → Run workflow**

Scheduled: every Sunday 02:00 UTC.

## Important limitation

The public OpenAPI currently returns only a small set of top-level notes for this topic.  
If a run finishes with `PDFs processed: 0`, the deep folder contents (the bulk of the PDFs) are not yet exposed by the `/knowledge/notes` endpoint.  
In that case we will need either a different API surface or a manual export path.
