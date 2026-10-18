# 321Convert

A small, private file converter. Drop in images, PDFs, spreadsheets, Word documents,
Markdown, HTML or text; pick a target format; download the result. No accounts, no stored
files, no third-party services.

**Live:** [three21convert.onrender.com](https://three21convert.onrender.com) · Maintained by
[ChardXBT](https://github.com/ChardXBT) · MIT licensed

![321Convert after converting a PNG to WebP and an XLSX to CSV](docs/screenshots/desktop-results.png)

The free Render instance sleeps when idle, so the first request after a quiet period can
take up to a minute. After that, conversions are fast.

## What it converts

| Input | Formats | Output |
| --- | --- | --- |
| Image | JPG, PNG, WebP, GIF, BMP, TIFF, HEIC/HEIF, AVIF, ICO | JPG, PNG, WebP, GIF, BMP, TIFF, AVIF, HEIC, ICO, PDF, TXT (OCR) |
| PDF | PDF | DOCX, TXT (with OCR for scanned pages), PNG, JPG |
| Spreadsheet | XLSX | CSV, PDF |
| CSV | CSV | XLSX |
| Word document | DOCX | PDF, TXT, HTML |
| HTML | HTML, HTM | PDF |
| Plain text | TXT | PDF, HTML |
| Markdown | MD, MARKDOWN | HTML, PDF |

Several files can be queued at once; each is converted in turn and downloaded individually.

### Images

- EXIF orientation is applied, then all other metadata (location, device) is dropped.
  Embedded colour profiles are kept when the output format supports them.
- Transparency is preserved for PNG, WebP, GIF, TIFF, AVIF and ICO; it is flattened onto
  white for JPG and PDF.
- Animated GIF/WebP and multi-page TIFF keep all frames when the output is GIF, WebP, TIFF or
  PDF (one page per frame); other outputs take the first frame.
- **Quality** (1–100) applies to JPG, WebP, AVIF and HEIC. **Maximum dimension** shrinks the
  longest side to the given size and never enlarges.
- ICO output is capped at 256 × 256 and includes the standard sizes up to that limit.
- Image → PDF places each image on an A4 page, fitted inside a margin.
- Image → TXT runs OCR (RapidOCR, English and Chinese models) on the picture and returns the
  recognised text; the result carries a note reminding you to check it.

### Documents and spreadsheets

- **PDF → DOCX** extracts selectable text (one page per PDF page, with embedded images) — it
  does not reproduce the original layout. **PDF → TXT** extracts text only. Pages with no
  selectable text (scans) are rendered and run through OCR, up to 10 pages or 60 seconds per
  file; the response notes which pages were recognised. **PDF → PNG/JPG** rasterises pages at
  144 DPI; multi-page PDFs return a ZIP with one image per page. Password-protected PDFs are
  refused with a clear message.
- **XLSX → CSV** exports one worksheet (the first, or the one you name) as UTF-8 with BOM so
  Excel opens it correctly; dates become ISO 8601 and formula-looking text is escaped to
  prevent spreadsheet formula injection. **XLSX → PDF** renders every worksheet (or a named one)
  as a table. **CSV → XLSX** detects the delimiter, converts numeric fields to numbers and stores
  everything else as literal text.
- **DOCX → PDF/HTML/TXT** preserves headings, paragraphs, alignment, indents and spacing,
  font sizes and colours, highlights, super/subscript, bold/italic/underline, bulleted and
  numbered lists, tables (widths, shading, merged cells), hyperlinks, page breaks, page size
  and margins, header/footer text and embedded images at their set sizes. Fonts are replaced
  by the bundled families, so pagination can differ from Word.
- **HTML → PDF** renders text, headings, lists, tables, images embedded as `data:` URIs, inline
  styles and the document's own `<style>` rules (classes and ids included). Scripts, external
  stylesheets, remote images, `@import`/`@font-face` and anything that could reach the network
  or a local file are removed; nothing is ever fetched.
- **Markdown → HTML/PDF** supports tables, fenced code and nested lists; raw HTML inside the
  Markdown is sanitised.
- Generated PDFs embed DejaVu Sans for Latin, Greek and Cyrillic, Droid Sans Fallback for
  Chinese and Japanese, and Noto Sans KR for Korean, so mixed-script documents render without
  missing glyphs.

## Limits

| Limit | Default |
| --- | --- |
| Upload size | 25 MB per file |
| Image size | 40 megapixels; animations up to 300 frames / 120 megapixels in total |
| PDF | 300 pages for text extraction; the first 50 pages for rasterising |
| OCR | 10 scanned pages or 60 seconds per file, whichever comes first |
| Spreadsheet | 500 000 cells; 2 000 rows per sheet in PDF output |
| HTML | 3 MB of markup; 200 KB of author CSS |
| Time | 90 seconds per conversion |
| Rate | 60 conversions per 10 minutes per client; 1 conversion at a time on Render |
| Memory | +256 MiB of writable memory per conversion (Linux); concurrency auto-clamped to fit the container's cgroup limit |

Over-limit requests fail fast with a plain-language error. Everything in the table is an
environment variable (see Deployment).

## Privacy and security

- Each request runs in its own temporary directory. The result is read into memory and the
  directory is deleted before the response is sent. There are no public download links,
  accounts, databases, analytics or persistent uploads.
- Every conversion runs in an isolated child process with a hard timeout and, on Linux, a
  bounded writable-memory budget (`CONVERSION_MEMORY_BYTES`, 256 MiB by default) on top of
  its current footprint. Exhausting that budget fails the conversion with a controlled 422
  instead of growing until the host runs out of memory. These limits reduce the blast radius
  of parser bugs and runaway allocations but are not an absolute guarantee — the OS decides
  what to kill under true memory pressure, and native parsing libraries run inside the child,
  so process isolation is a reliability boundary, not a hardened security sandbox.
- Uploads are validated by extension and content (PDF header, Office ZIP structure and
  size/path checks, text files must not contain NUL bytes, images must decode as one of the
  accepted formats). Decompression bombs are refused.
- HTML and Markdown input is sanitised with an allow-list, and the PDF renderer is locked to a
  read-only font directory with network access disabled.
- Responses carry a strict Content-Security-Policy (nonce-based for the single inline
  script), `frame-ancestors 'none'`, HSTS, `Referrer-Policy: no-referrer` and the usual
  hardening headers. POST requests must be same-origin; an in-memory per-IP rate limit and a
  concurrency cap protect the service.
- Error messages never include file names, file contents or parser internals; logs record only
  the conversion type, timing, sizes and exception class.

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## HTTP API

The UI uses the same endpoints you can call directly.

```
GET  /api/formats            → JSON describing families, outputs and options
POST /api/convert            multipart/form-data: file=<upload> target=<ext> [quality] [max_dimension] [sheet_name] [title]
GET  /health                 → {"status": "ok", "version": "<git sha>"}
```

A successful `POST /api/convert` returns the converted file as an attachment with
`Content-Disposition` (UTF-8 filename) and an `X-Conversion-Notes` header holding a JSON list
of short notes such as `"Transparent areas were flattened to white."`. Errors are JSON:
`{"success": false, "error": "…"}` with status 400 (bad request), 413 (too large), 422
(could not convert), 429 (rate limited), 503 (busy) or 504 (timed out).

```sh
curl -F file=@photo.heic -F target=jpg -F quality=85 https://three21convert.onrender.com/api/convert -o photo.jpg
```

The original `POST /convert` and `POST /document/convert` routes still work as thin aliases.

## Local setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m conversions.ocr_models
python app.py
```

`python -m conversions.ocr_models` downloads the pinned OCR model files and verifies their
SHA-256 checksums. It runs during the Render build and again inside `gunicorn.conf.py`'s
`on_starting` hook as a startup fallback (in case the platform does not sync the build
command): only the model files are fetched and verified — no uploads ever leave the service —
and startup fails if they are missing or corrupt, so there is no runtime model download
during requests.

Open `http://127.0.0.1:5000`. Conversions run in short-lived child processes: Linux uses a
pre-warmed fork server, and on Windows/macOS one idle worker is kept pre-spawned so there is
no start-up pause. Set `CONVERSION_ISOLATION=inline` to run conversions in-process while
debugging.

## Tests

```powershell
ruff check . ; ruff format --check .
pytest -q                 # unit, API and security tests (fast, in-process conversions)
playwright install chromium
pytest -m e2e -q          # browser tests against a live local server
python scripts/capture_screenshots.py [--base-url URL]   # refresh docs/screenshots
```

CI runs the same steps on Python 3.12 and 3.13, a Gunicorn smoke test that boots the exact
production command and converts files through it, and `pip-audit`; Dependabot keeps
dependencies current. The design is documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Deployment

[render.yaml](render.yaml) is a Render Blueprint: a single Python web service running Gunicorn
with a health check on `/health`. No secrets are required. Pushing to `master` deploys.

| Variable | Default | Purpose |
| --- | ---: | --- |
| `MAX_UPLOAD_BYTES` | 26214400 | Maximum request size |
| `MAX_OUTPUT_BYTES` | 78643200 | Maximum returned file size |
| `CONVERSION_TIMEOUT` | 90 | Seconds before a conversion is killed |
| `MAX_CONCURRENT_CONVERSIONS` | 2 (1 on Render) | Requested conversions at once; auto-clamped down by the cgroup memory limit |
| `CONVERSION_MEMORY_BYTES` | 268435456 | Extra writable-memory budget each conversion child may grow (Linux) |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW` | 60 / 600 | Per-client rate limit |
| `MAX_IMAGE_PIXELS`, `MAX_FRAMES`, `MAX_PDF_PAGES`, `MAX_PDF_RENDER_PAGES`, `MAX_SPREADSHEET_CELLS`, `MAX_PDF_TABLE_ROWS`, `MAX_HTML_BYTES`, `MAX_CSS_BYTES` | see `core/config.py` | Content limits |
| `OCR_MAX_PAGES` / `OCR_TIME_BUDGET` / `OCR_RENDER_SCALE` / `OCR_THREADS` | 10 / 60 / 1.4 / 1 | OCR page cap, time budget (s), render scale (1.4 ≈ 100 DPI) and ONNX threads |
| `CONVERSION_ISOLATION` | process | `process` or `inline` |
| `TRUST_PROXY` | false (true on Render) | Trust one proxy hop for client IPs |
| `LOG_LEVEL` | INFO | Logging verbosity |

## Known limitations

- OCR uses general-purpose English/Chinese models; handwriting, very small print and other
  scripts are recognised less reliably, each scanned page costs several seconds of CPU, and
  the text detector analyses a reduced-resolution image (long side ≤ 736 px) to stay within
  the memory budget.
- Generated PDFs use the bundled fonts, so a document's own typefaces are substituted and
  page breaks can fall differently from Word or a browser.
- The free Render tier has a cold start of up to a minute after inactivity.

## Legal

[Terms of Service](TERMS.md) · [MIT License](LICENSE) · [Code of Conduct](CODE_OF_CONDUCT.md)
