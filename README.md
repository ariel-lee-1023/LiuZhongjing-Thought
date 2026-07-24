# LiuZhongjing-Thought

Archive of **刘仲敬思想 (LZJT)** PDFs → clean Markdown.

> **Intellectual Property Notice**  
> All original texts by **Liu Zhongjing (刘仲敬)** remain his exclusive intellectual property.  
> This repository claims no ownership of the underlying content.  
> See [NOTICE.md](NOTICE.md) for the full bilingual disclaimer.

## How to use (drop-folder workflow)

1. Download the PDFs from the three LZJT sub-folders on biji.com.
2. Upload them into the matching folders in this repo:

```
incoming/
├── LZJ-Writings/                       
├── LZJ-FiguresCritique/                 
└── LZJ-Lec-HistPhil_MoralPhil_Epist/    
```

3. Push (or just upload via the GitHub web UI).  
   The Action will automatically:
   - convert every `*.pdf` with MarkItDown
   - write the `.md` files into the corresponding place under `content/LZJT/`
   - delete the source PDF (keeps the repo light)
   - commit & push the result

You can also trigger it manually: **Actions → Convert incoming LZJT PDFs → Run workflow**.

## Output layout

```
content/
└── LZJT/
    ├── LZJ-Writings/
    │   └── <original-name>.md
    ├── LZJ-FiguresCritique/
    │   └── <original-name>.md
    └── LZJ-Lec-HistPhil_MoralPhil_Epist/
        └── <original-name>.md
```

## Notes

- MarkItDown uses pdfminer (text extraction). Layout-heavy academic PDFs may need light post-editing.
- The old 得到大脑 OpenAPI path is no longer used — the public API cannot see the deep folder PDFs.
