# PDF Parsing — docling + liteparse + pdfplumber

Three tools for PDF extraction. Each has a sweet spot — use the right one (or combine them).

## When to use what

| Task | Tool |
|------|------|
| **Tables** (especially borderless financial) | **docling** — AI layout model (TableFormer) handles ársreikningar with no visible borders |
| **Structured document** (headings, sections, reading order) | **docling** — classifies every element with semantic labels |
| **Figure/image extraction** as PIL images | **docling** with `generate_picture_images=True` |
| **Markdown/HTML export** | **docling** — `export_to_markdown()`, `export_to_html()` |
| **Text with font info** (name, size per fragment) | **liteparse** — `.fontName`, `.fontSize` on each TextItem |
| **Page screenshots** at configurable DPI | **liteparse** — `parser.screenshot()` |
| **Quick text extraction** with coordinates | **liteparse** — fast, simple API |
| **Vector graphics detection** (rects, curves, lines) | **pdfplumber** — detects infographic vs text pages |
| **Character-level access** | **pdfplumber** |
| **DOCX, PPTX, XLSX, HTML** | **docling** — same API for all formats |

## docling (primary tool)

IBM's AI-powered document parser. 97.9% table accuracy on benchmarks. The heavy hitter.

```bash
uv pip install docling   # v2.74.0
```

### Basic usage

```python
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

# Configure — ALWAYS disable OCR for native/digital PDFs
po = PdfPipelineOptions()
po.do_ocr = False                      # most Icelandic public PDFs are native text
po.do_table_structure = True           # TableFormer — the killer feature
po.generate_picture_images = True      # extract figures as PIL images

converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=po)}
)

result = converter.convert("report.pdf")
doc = result.document
```

### Exports

```python
doc.export_to_markdown()    # clean structured markdown
doc.export_to_text()        # plain text
doc.export_to_html()        # full HTML
doc.export_to_dict()        # JSON-serializable dict

# Save with images
doc.save_as_markdown("out.md", image_mode=ImageRefMode.REFERENCED)
doc.save_as_json("out.json")   # images base64-embedded by default

# Per-page markdown
doc.export_to_markdown(page_no=3)
```

### Tables

```python
for table in doc.tables:
    df = table.export_to_dataframe(doc)   # pandas DataFrame
    md = table.export_to_markdown(doc)    # markdown table
    html = table.export_to_html(doc)      # HTML table

    # Cell-level access
    for row in table.data.grid:
        for cell in row:
            print(cell.text, cell.column_header, cell.row_header)
            print(cell.bbox)  # BoundingBox(l, t, r, b)
```

docling finds tables that pdfplumber misses entirely — borderless financial tables where alignment is the only structure. Critical for Icelandic ársreikningar.

### Figures

```python
for pic in doc.pictures:
    if pic.image:
        pil_img = pic.image.pil_image   # PIL.Image (property, not method)
        pil_img.save(f"figure_{pic.self_ref}.png")
    # Position
    for prov in pic.prov:
        print(f"Page {prov.page_no}, bbox: {prov.bbox}")
```

### Document tree & element types

```python
from docling.datamodel.document import DocItemLabel

for item, level in doc.iterate_items():
    label = item.label  # DocItemLabel enum
    # Labels: text, section_header, title, list_item, table, picture,
    #         caption, footnote, page_header, page_footer, chart, formula, code
    if hasattr(item, 'prov') and item.prov:
        bbox = item.prov[0].bbox   # BoundingBox(l, t, r, b, coord_origin=BOTTOMLEFT)
        page = item.prov[0].page_no

# Heading levels
for item, level in doc.iterate_items():
    if isinstance(item, SectionHeaderItem):
        print(f"H{item.level}: {item.text}")
```

### Page range + batch

```python
# Parse only pages 1-10
result = converter.convert("big.pdf", page_range=(1, 10))

# Batch convert
for result in converter.convert_all(["a.pdf", "b.pdf", "c.pdf"]):
    print(result.document.name, result.status)
```

### Pipeline options reference

| Option | Default | Notes |
|--------|---------|-------|
| `do_ocr` | True | **Disable for native PDFs** — saves ~3-5s/page |
| `do_table_structure` | True | TableFormer (ACCURATE mode). Set `mode=TableFormerMode.FAST` for speed |
| `generate_picture_images` | False | Extract PictureItem as PIL images |
| `generate_page_images` | False | Full-page rasters |
| `do_picture_classification` | False | AI picture type classification |
| `do_picture_description` | False | VLM captioning (SmolVLM-256M) |
| `do_chart_extraction` | False | Chart data extraction |

### Confidence scores

```python
conf = result.confidence
print(conf.parse_score)    # 1.0 = native PDF parsed cleanly
print(conf.layout_score)   # 0.8–0.9 typical
print(conf.mean_grade)     # QualityGrade.GOOD / EXCELLENT
```

### Icelandic OCR (scanned PDFs only)

```python
from docling.datamodel.pipeline_options import OcrMacOptions  # macOS

po.do_ocr = True
po.ocr_options = OcrMacOptions(lang=["is-IS", "en-US"])  # Apple Vision
# Tesseract alternative: lang=["isl"] (needs isl.traineddata)
```

Most Icelandic public PDFs (skatturinn, sedlabanki, Hagstofan) are native text — `do_ocr=False` is correct.

### Performance (M-series Mac)

| Config | 32 pages |
|--------|----------|
| No OCR, no tables | ~8s |
| No OCR, with tables | ~15-25s |
| First call (model loading) | +5-10s overhead |

---

## liteparse

LlamaIndex's fast local parser. Best for: font-level detail, page screenshots, quick text+coords.

```python
from liteparse import LiteParse

parser = LiteParse()

# Parse (no OCR for native PDFs)
result = parser.parse("doc.pdf", ocr_enabled=False)

for page in result.pages:
    for item in page.textItems:
        # Per-fragment font info — docling doesn't have this
        print(item.text, item.x, item.y, item.fontName, item.fontSize)
```

### CLI

```bash
lit parse doc.pdf --format json --no-ocr -o out.json
lit parse doc.pdf --target-pages "1-5" --ocr-language is
lit screenshot doc.pdf -o ./shots --dpi 200
lit batch-parse ./pdfs ./outputs --recursive
```

### Screenshots (docling can't do this as easily)

```python
result = parser.screenshot("doc.pdf", output_dir="./shots", dpi=200)
for s in result.screenshots:
    print(f"Page {s.page_num}: {s.image_path}")
```

### Data model

- `ParseResult.pages` → list of `ParsedPage`
- `ParsedPage`: `.pageNum`, `.width`, `.height`, `.text`, `.textItems`, `.boundingBoxes`
- `TextItem`: `.text`, `.x`, `.y`, `.width`, `.height`, `.fontName`, `.fontSize`, `.confidence`
- `BoundingBox`: `.x1`, `.y1`, `.x2`, `.y2`

Coordinates: top-left origin, PDF points (1pt = 1/72 inch). A4 = 595 x 842.

---

## pdfplumber

Low-level PDF access. Best for: vector graphics detection, character-level parsing, line/rect/curve geometry.

```python
import pdfplumber

with pdfplumber.open("doc.pdf") as pdf:
    for page in pdf.pages:
        # Vector graphics — detect infographics
        images = page.images or []     # embedded raster images
        rects = page.rects or []       # rectangles
        curves = page.curves or []     # bezier curves (SVG-like vector art)
        lines = page.lines or []       # line segments

        # Page type heuristic
        text = page.extract_text() or ""
        if len(curves) > 10 and not images:
            page_type = "infographic"
        elif images and len(text) < 200:
            page_type = "photo"
        elif images:
            page_type = "mixed"
        else:
            page_type = "text"
```

pdfplumber's table extraction (`page.extract_tables()`) requires visible borders — it fails on borderless financial tables. Use docling for those.

---

## Combined extraction pattern

```python
import liteparse
import pdfplumber
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

def extract_pdf(path):
    """Full extraction: structure (docling) + fonts (liteparse) + graphics (pdfplumber)."""

    # 1. docling — structure, tables, figures
    po = PdfPipelineOptions(do_ocr=False, generate_picture_images=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=po)}
    )
    doc_result = converter.convert(path)
    doc = doc_result.document

    # 2. liteparse — font info + screenshots
    lp = liteparse.LiteParse()
    lp_result = lp.parse(path, ocr_enabled=False)
    screenshots = lp.screenshot(path, output_dir="/tmp/shots", dpi=200)

    # 3. pdfplumber — vector graphics detection
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            curves = page.curves or []
            if len(curves) > 10:
                print(f"Page {i+1}: infographic ({len(curves)} curves)")

    return {
        "markdown": doc.export_to_markdown(),
        "tables": [t.export_to_dataframe(doc) for t in doc.tables],
        "figures": [p.image.pil_image for p in doc.pictures if p.image],
        "font_map": {
            p.pageNum: [(t.text, t.fontName, t.fontSize) for t in p.textItems]
            for p in lp_result.pages
        },
        "screenshots": {s.page_num: s.image_path for s in screenshots.screenshots},
    }
```

## Caveats

- **Ligature artifacts**: Some PDFs encode `ff` → `f/f_short` in font — all three tools pass this through. Not fixable without font-level glyph remapping.
- **Icelandic numbers**: Financial PDFs use dot-thousands (`1.279.828`) and parenthetical negatives `(1.279.828)`. All tools preserve these as strings — post-process with `text.replace(".", "").replace("(", "-").replace(")", "")`.
- **Coordinate systems differ**: liteparse uses top-left origin; docling BoundingBox uses bottom-left (`coord_origin=BOTTOMLEFT`). Convert with `top_y = page_height - bbox.b`.
- **docling model loading**: First call in a process loads TableFormer (~5-10s). Reuse the `DocumentConverter` instance.
- **liteparse under the hood**: Calls `npx @llamaindex/liteparse` — requires Node.js.
