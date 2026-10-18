# Architecture

321Convert is a small Flask service that converts one uploaded file per request and
returns the result as a private attachment. Nothing is stored. This document describes
the design that the code must follow; keep it accurate when you change behaviour.

## Layout

```
app.py                  Flask app (module-level `app` for gunicorn `app:app`): routes, validation, headers
core/
  config.py             All tunables, read once from environment variables
  registry.py           Families, outputs, options: the single source of truth for "what converts to what"
  uploads.py            Filename sanitising, extension -> family, content sniffing, Office archive checks
  runner.py             Runs one conversion in an isolated child process with a hard timeout
  errors.py             ConversionError (safe, user-facing) and friends
conversions/
  __init__.py           CONVERTERS: {(family, output_ext): callable} -- light; heavy libraries import lazily
  images.py             Pillow (+ pillow-heif): any raster image -> jpg/png/webp/gif/bmp/tiff/avif/ico/pdf
  pdf.py                pypdf + pypdfium2: pdf -> docx/txt/png/jpg
  spreadsheets.py       openpyxl: xlsx -> csv/pdf, csv -> xlsx
  documents.py          python-docx, nh3, Markdown: docx -> pdf/txt/html, html/md/txt -> pdf/html
  pdf_render.py         Shared xhtml2pdf rendering: base CSS, embedded DejaVu fonts, locked-down resource policy
  fonts/                DejaVu Sans TTFs + LICENSE (Unicode coverage for generated PDFs)
static/                 app.js, styles.css, favicon.svg (no framework, no build step)
templates/index.html    Single page; the registry is embedded as JSON for the UI
tests/                  pytest suite; tests/e2e holds Playwright browser tests
```

## Request flow

1. `POST /api/convert` receives multipart form data: `file`, `target` (output extension) and
   optional option fields (see Options).
2. `core.uploads` sanitises the original filename, derives the extension, maps it to a family,
   and saves the upload as `input.<ext>` inside a fresh `tempfile.TemporaryDirectory`.
   Content sniffing rejects obviously mislabelled files (PDF header, ZIP/Office structure,
   text files containing NUL bytes).
3. `core.registry` validates `(family, target)` and coerces/validates the options.
4. `core.runner.run()` executes the converter. In `process` mode (production default) the
   converter runs in a child process; the parent waits up to `CONVERSION_TIMEOUT` seconds and
   kills the child on timeout. A `BoundedSemaphore(MAX_CONCURRENT_CONVERSIONS)` bounds how
   many conversions run at once; callers that cannot acquire it within `BUSY_WAIT_SECONDS`
   receive `503` with `Retry-After`.
5. The converter writes its output into the same temporary directory and returns a
   `ConversionResult(path, extension, notes)`. The output extension may differ from the
   requested target (multi-page PDF -> images returns a `.zip`).
6. The route reads the output into memory (bounded by `MAX_OUTPUT_BYTES`), the temporary
   directory is deleted, and the bytes are sent with `Content-Disposition: attachment`,
   a correct `Content-Type`, and `X-Conversion-Notes` (JSON list of short, human-readable notes
   such as "Transparent areas were flattened to white").

Errors are JSON: `{"success": false, "error": "<message>"}`. Messages shown to users come
only from `ConversionError`/`RequestValidationError`; every other exception maps to a generic
message and is logged by type name only (never with filenames or file content).

## Registry (`core/registry.py`)

A *family* groups input extensions that share converters and options.

| Family | Input extensions | Outputs |
| --- | --- | --- |
| `image` | jpg, jpeg, png, webp, gif, bmp, tif, tiff, heic, heif, avif, ico | jpg, png, webp, gif, bmp, tiff, avif, ico, pdf |
| `pdf` | pdf | docx, txt, png, jpg |
| `spreadsheet` | xlsx | csv, pdf |
| `csv` | csv | xlsx |
| `docx` | docx | pdf, txt, html |
| `html` | html, htm | pdf |
| `text` | txt | pdf, html |
| `markdown` | md, markdown | html, pdf |

Options are declared once and attached by family and/or output:

| Option | Type / range | Default | Applies when |
| --- | --- | --- | --- |
| `quality` | int 1–100 | 82 | output is jpg, webp or avif |
| `max_dimension` | int 16–10000 px, optional | none | family is `image` (longest side; never upscales) |
| `sheet_name` | str ≤ 100 chars, optional | first sheet (csv) / all sheets (pdf) | family is `spreadsheet` |
| `title` | str ≤ 120 chars, optional | source filename | family is `text` or `markdown` and output is html |

`registry.describe()` returns the JSON the UI and `GET /api/formats` use:
`{"max_upload_mb", "accept", "families": [{"id","label","extensions","outputs":[{"ext","label"}],"options":[...]}], "options": {...}}`.

Converters are looked up by `(family, output_ext)` in `conversions.CONVERTERS` and called as
`convert(input_path: Path, output_path: Path, options: dict) -> ConversionResult`. The
`output_path` already carries the target extension; a converter that produces something else
(e.g. a zip) writes beside it and returns the actual path.

## Isolation and limits (`core/runner.py`)

- `CONVERSION_ISOLATION=process|inline`. Production uses `process`; tests use `inline` except
  for the runner tests themselves.
- The multiprocessing context is `forkserver` where available (Linux) with
  `set_forkserver_preload(["conversions.warm"])` so children start with the heavy libraries
  already imported; `spawn` elsewhere. The forkserver is started eagerly at app start so the
  first conversion is not slow.
- The child sends a single message back through a pipe: `{"ok": True, "result": {...}}` or
  `{"ok": False, "user_message": str|None, "error_type": str}`. A child that exits without a
  message is reported as a crash. Parent-side, `ConversionTimeout` and `ConversionCrashed`
  both become a generic 422/504 message for the user.
- Decompression-bomb protection: `Image.MAX_IMAGE_PIXELS = 40_000_000` and
  `DecompressionBombWarning` raised as an error. Animated inputs are additionally bounded by
  `MAX_FRAMES` and a total pixel budget; beyond it only the first frame is kept and a note is
  returned.
- Documents: `MAX_PDF_PAGES` (text extraction), `MAX_PDF_RENDER_PAGES` (rasterising),
  `MAX_SPREADSHEET_CELLS`, `MAX_PDF_TABLE_ROWS`, `MAX_HTML_BYTES`, `MAX_EMBEDDED_IMAGE_BYTES`.
- Office uploads are checked as ZIP archives before parsing: member count, total uncompressed
  size, path traversal, and the presence of `[Content_Types].xml` plus `xl/workbook.xml` or
  `word/document.xml`.

## PDF generation (`conversions/pdf_render.py`)

All HTML -> PDF rendering goes through `render_pdf(body_html, output_path, *, title, landscape)`.
It wraps the body in a fixed document with the base stylesheet and `@font-face` rules for the
bundled DejaVu Sans family, and calls `pisa.CreatePDF(..., resource_policy=POLICY)` where

```python
POLICY = ResourceAccessPolicy.server(base_dir=FONT_DIR, allow_remote=False, max_render_seconds=...)
```

so the renderer can read only the font directory, never the network, and never other local
files. User-supplied HTML is sanitised with `nh3` first (allow-listed tags/attributes, inline
`style` values filtered to drop `url(`, `expression(`, `@import`, `javascript:`; `<style>` and
`<script>` blocks removed; `http(s)` image sources dropped, `data:` images allowed and bounded
by the policy's pixel/byte limits).

## HTTP hardening (`app.py`)

- `Content-Security-Policy` with a per-request nonce for the one inline script (theme
  bootstrap), everything else `'self'`; `frame-ancestors 'none'`, `object-src 'none'`,
  `base-uri 'none'`, `form-action 'self'`.
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy`, COOP/CORP `same-origin`, HSTS when the request is secure.
- POST requests must be same-origin: `Origin` must match the host when present, and
  `Sec-Fetch-Site` must not be `cross-site`.
- In-memory per-IP rate limit (`RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW`) with a bounded
  client map and `Retry-After`.
- `MAX_CONTENT_LENGTH` bounds uploads; `MAX_OUTPUT_BYTES` bounds responses.
- Static assets are served with a content hash in the query string and
  `Cache-Control: public, max-age=31536000, immutable`; HTML and API responses are `no-store`.
- `/health` returns `{"status": "ok", "version": <short git sha or "dev">}` using
  `RENDER_GIT_COMMIT` when present, so a deploy can be verified from outside.

## Frontend (`static/app.js`, `static/styles.css`, `templates/index.html`)

Plain ES2020, no build step, CSP-compatible (no inline handlers, no `innerHTML` with user data).

- One drop zone accepts multiple files. Each file becomes a row showing an extension badge,
  name, size, a "Convert to" select populated from the registry for its family, and a status
  column (ready / uploading with progress / converting / done with Download / error with
  Retry). Unsupported files get an inline explanation and no select.
- The options panel shows only the options relevant to the current rows and targets (union),
  and applies to all rows.
- "Convert" processes rows sequentially with `XMLHttpRequest` (for upload progress). Results
  are object URLs, revoked when a row is removed or the list is cleared.
- Theme: a nonce'd inline script sets `data-theme` on `<html>` before first paint from
  `localStorage` or `prefers-color-scheme`; a toggle button persists the choice.
- Accessibility: keyboard-operable drop zone, labelled controls, `aria-live` status summary,
  visible focus rings, reduced-motion support, AA contrast in both themes.

## Deployment

Render runs `gunicorn` from `render.yaml`/`Procfile` with one worker and a few threads; the
worker is mostly waiting on child processes, so threads are cheap. `--timeout` is longer than
`CONVERSION_TIMEOUT` plus upload time. Health checks hit `/health`. No secrets are needed.

## Tests

- `pytest` unit and API tests run with `CONVERSION_ISOLATION=inline` for speed; `tests/test_runner.py`
  exercises `process` mode (success, timeout kill, crash isolation, busy 503).
- `tests/e2e` runs Playwright against a live local server (`pytest -m e2e`), covering the full
  browser flow, mobile layout, theme persistence, dialogs and keyboard access.
- CI (`.github/workflows/ci.yml`) runs ruff, the unit suite on Python 3.12 and 3.13, the e2e
  suite, and `pip-audit`. Dependabot keeps pip and Actions dependencies current.
