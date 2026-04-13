# LiteParse — PDF Parsing & Visual Extraction

Fast, local PDF parser (LlamaIndex) for text extraction with bounding box coordinates, page screenshots, and visual element detection. Wraps a Node.js CLI (`lit`) via a Python wrapper.

## Installation

```bash
uv pip install liteparse
# CLI available as `lit` (requires Node.js/npx)
```

Current version: 1.2.1. Docs: https://developers.llamaindex.ai/liteparse/

## CLI Usage

```bash
# Parse PDF to text
lit parse document.pdf

# Parse to JSON with bounding boxes
lit parse document.pdf --format json -o output.json

# Parse specific pages, no OCR (native PDFs)
lit parse document.pdf --format json --no-ocr --target-pages "1-5,10"

# Screenshot pages at high DPI
lit screenshot document.pdf -o ./screenshots --dpi 200

# Batch parse a directory
lit batch-parse ./pdfs ./outputs --recursive --extension ".pdf"
```

### CLI Flags (lit parse)

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output` | stdout | Output file path |
| `--format` | `text` | `text` or `json` |
| `--no-ocr` | false | Disable OCR (use for native/digital PDFs) |
| `--ocr-language` | `en` | Language code (`is` for Icelandic) |
| `--target-pages` | all | Page ranges: `"1-5,10,15-20"` |
| `--dpi` | 150 | Rendering resolution |
| `--num-workers` | CPU-1 | Parallel OCR workers |
| `--max-pages` | 10000 | Page limit |
| `--password` | | For encrypted PDFs |
| `-q, --quiet` | false | Suppress progress |

## Python API

```python
from liteparse import LiteParse

parser = LiteParse()

# Parse — use ocr_enabled=False for native PDFs (much faster)
result = parser.parse(
    "document.pdf",
    ocr_enabled=False,       # Skip OCR for digital PDFs
    ocr_language="is",       # Icelandic OCR when needed
    target_pages="1-10",     # Optional page selection
    dpi=150,                 # Resolution for OCR
)

# Full text
print(result.text)

# Per-page access
for page in result.pages:
    print(f"Page {page.pageNum}: {page.width}x{page.height}")
    print(f"  Text items: {len(page.textItems)}")
    print(f"  Bounding boxes: {len(page.boundingBoxes)}")
```

### Data Model

**ParseResult**
- `.text` — full document text
- `.pages` — list of `ParsedPage`

**ParsedPage**
- `.pageNum` — 1-indexed page number
- `.width`, `.height` — page dimensions (PDF points)
- `.text` — page text
- `.textItems` — list of `TextItem` with position data
- `.boundingBoxes` — list of `BoundingBox` regions

**TextItem** — individual text fragment with coordinates
- `.text` — the text content
- `.x`, `.y` — position (top-left origin, PDF points)
- `.width`, `.height` — dimensions
- `.fontName` — font identifier
- `.fontSize` — font size
- `.confidence` — OCR confidence (when OCR enabled)

**BoundingBox** — rectangular region
- `.x1`, `.y1`, `.x2`, `.y2` — corner coordinates

### Screenshots

```python
result = parser.screenshot(
    "document.pdf",
    output_dir="./screenshots",
    target_pages="1,5,10",
    dpi=200,
    image_format="png",     # or "jpg"
)

for s in result.screenshots:
    print(f"Page {s.page_num}: {s.image_path}")
```

**ScreenshotBatchResult**
- `.screenshots` — list of `ScreenshotResult`
  - `.page_num`, `.image_path`, `.image_bytes`

## Combining with pdfplumber for Visual Detection

liteparse extracts text with coordinates. pdfplumber detects vector graphics (rects, curves, lines) and embedded images. Combine both for full visual element extraction:

```python
import liteparse
import pdfplumber

parser = liteparse.LiteParse()
result = parser.parse("doc.pdf", ocr_enabled=False)

with pdfplumber.open("doc.pdf") as pdf:
    for lp_page in result.pages:
        pp_page = pdf.pages[lp_page.pageNum - 1]
        
        images = pp_page.images or []      # Embedded raster images
        rects = pp_page.rects or []        # Rectangles
        curves = pp_page.curves or []      # Bezier curves (SVG-like)
        lines = pp_page.lines or []        # Line segments
        
        # Page classification heuristic
        text_len = len(lp_page.text.strip())
        if len(curves) > 10 and not images:
            page_type = "infographic"      # Vector graphics
        elif images and text_len < 200:
            page_type = "photo_page"
        elif images:
            page_type = "mixed"            # Text + images
        else:
            page_type = "text"
```

## Caveats

- **OCR is slow**: ~3-5 sec/page. Use `ocr_enabled=False` for native/digital PDFs.
- **Text items are fragments**: Words/phrases, not lines. Reconstruct lines by grouping items with similar `y` coordinates.
- **Coordinates**: Origin is top-left, units are PDF points (1/72 inch). Page 16 at `width=595` is A4 width.
- **Icons/emojis**: Vector icon fonts render as empty strings or garbage characters in textItems.
- **No image extraction**: liteparse doesn't extract embedded images as files. Use pdfplumber or `pdfimages` CLI for that.
- **Under the hood**: Python wrapper calls `npx @llamaindex/liteparse` — requires Node.js.
