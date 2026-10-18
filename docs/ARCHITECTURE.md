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
  resources.py          cgroup memory detection, concurrency clamp, per-child writable-memory cap
  runner.py             Runs one conversion in an isolated child process with a hard timeout
  errors.py             ConversionError (safe, user-facing) and friends
conversions/
  __init__.py           CONVERTERS: {(family, output_ext): callable} -- light; heavy libraries import lazily
  images.py             Pillow (+ pillow-heif): any raster image -> jpg/png/webp/gif/bmp/tiff/avif/heic/ico/pdf
  pdf.py                pypdf + pypdfium2: pdf -> docx/txt/png/jpg, with OCR fallback for scanned pages
  ocr.py                RapidOCR (onnxruntime): scanned-page and image text recognition, engine loaded lazily
  ocr_models.py         Pinned OCR model paths, download URLs and SHA-256 checks; build-time preparation
  spreadsheets.py       openpyxl: xlsx -> csv/pdf, csv -> xlsx
  documents.py          python-docx, nh3, Markdown: docx -> pdf/txt/html, html/md/txt -> pdf/html
  pdf_render.py         Shared xhtml2pdf rendering: base CSS, script-aware fonts, sanitised author CSS,
                        locked-down resource policy
  fonts/                Bundled TTFs + licenses: DejaVu Sans, Droid Sans Fallback (CJK), Noto Sans KR (Hangul)
gunicorn.conf.py        Gunicorn on_starting hook: verifies/prepares OCR models before accepting traffic
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
   kills the child on timeout. A `BoundedSemaphore` bounds how many conversions run at once;
   its size is `resources.concurrency_limit()`, which starts from
   `MAX_CONCURRENT_CONVERSIONS` and clamps it down to fit the container's cgroup memory
   limit (192 MiB reserved for the web server, forkserver, uploads and responses, then one
   `CONVERSION_MEMORY_BYTES` slot per concurrent conversion — so a 512 MiB instance allows
   exactly one). Callers that cannot acquire it within `BUSY_WAIT_SECONDS` receive `503`
   with `Retry-After`.
5. The converter writes its output into the same temporary directory and returns a
   `ConversionResult(path, extension, notes)`. The output extension may differ from the
   requested target (multi-page PDF -> images returns a `.zip`).
6. The route stats the output and rejects it with 422 when it exceeds `MAX_OUTPUT_BYTES`
   before reading, then reads it into memory (the post-read size check is kept as defence
   in depth), the temporary
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
| `image` | jpg, jpeg, png, webp, gif, bmp, tif, tiff, heic, heif, avif, ico | jpg, png, webp, gif, bmp, tiff, avif, heic, ico, pdf, txt |
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
| `quality` | int 1–100 | 82 | output is jpg, webp, avif or heic |
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
- Workers use a job-over-pipe protocol: `context.Pipe` carries the job tuple into the child
  and a second pipe carries exactly one message back: `{"ok": True, "result": {...}}` or
  `{"ok": False, "user_message": str|None, "error_type": str}`. A child that exits without a
  message is reported as a crash. Parent-side, `ConversionTimeout` and `ConversionCrashed`
  both become a generic 422/504 message for the user.
- `resources.limit_memory()` runs in the child before the converter: on Linux it caps
  `RLIMIT_DATA` at the child's current writable data (`VmData`) plus
  `CONVERSION_MEMORY_BYTES` (256 MiB by default), so a runaway allocation becomes a
  `MemoryError` — reported as a controlled 422 ("The conversion needs too much memory. Try
  a smaller file.") — instead of growing until the container OOM-kills the whole service.
  This allows read-only shared-library mappings without granting the same headroom for
  private writable buffers. Container accounting also includes file cache and other
  processes. Applying the limit fails the conversion loudly; these bounds reduce the blast
  radius but cannot promise which process the kernel kills under true memory pressure, and
  native parsers inside the child are not a security sandbox.
  `OPENBLAS_NUM_THREADS`/`OMP_NUM_THREADS` are defaulted to 1 in `config` before any
  numerical library loads. `MALLOC_ARENA_MAX=1` is inherited by forkserver/spawn children
  to avoid additional glibc arenas reserving writable address space under the memory cap.
- On `spawn` platforms one idle worker is kept pre-spawned: after each job is dispatched a
  fresh worker is started in the background (never more than one waiting), and `warm_up()`
  pre-spawns it instead of importing the heavy libraries into the web process. A dispatch
  takes a waiting worker when it is still alive, so back-to-back conversions skip process
  start-up. Idle workers are daemons, exit cleanly when their pipes close, and are not used
  on `forkserver` platforms (each waiting child would hold the preloaded libraries in RAM).
- Decompression-bomb protection: `Image.MAX_IMAGE_PIXELS = 40_000_000` and
  `DecompressionBombWarning` raised as an error. Animated inputs are additionally bounded by
  `MAX_FRAMES` and a total pixel budget; beyond it only the first frame is kept and a note is
  returned.
- Documents: `MAX_PDF_PAGES` (text extraction), `MAX_PDF_RENDER_PAGES` (rasterising),
  `MAX_SPREADSHEET_CELLS`, `MAX_PDF_TABLE_ROWS`, `MAX_HTML_BYTES`, `MAX_EMBEDDED_IMAGE_BYTES`,
  `MAX_CSS_BYTES` (author stylesheets).

## OCR (`conversions/ocr.py`)

Scanned pages produce little or no selectable text. When a PDF page yields fewer than
`OCR_MIN_TEXT_CHARS` non-space characters (12 by default), `pdf -> txt` and `pdf -> docx`
render it with pypdfium2 at `OCR_RENDER_SCALE` (~100 DPI) and run RapidOCR on the bitmap.
`image -> txt` does the same for a single raster input (first frame, EXIF orientation
applied). The engine is imported and constructed lazily, once per worker process — never
in `conversions.preload()` or at module import — with `OCR_THREADS=1` ONNX intra/inter-op
thread caps, CPU memory arena disabled, a `max`-mode detector capped at 736 px and batch
size 1, so it stays cheap on small instances. The model files are pinned in
`conversions/ocr_models.py`, downloaded and SHA-256-verified during the build
(`python -m conversions.ocr_models` in `render.yaml`, plus `gunicorn.conf.py`'s
`on_starting` hook as a startup fallback that fails readiness if they are missing or
corrupt) — only the model files are fetched, uploads never leave the service, and there is
no runtime model download during requests.
Recognition is bounded by `OCR_MAX_PAGES` (10) and `OCR_TIME_BUDGET` (60 s wall-clock,
checked before each page, predictive of the previous page's cost); hits below score 0.5
are dropped and images are downscaled to a 1800 px long side before the detector sees them.
Notes tell the user when text was OCR'd and when OCR stopped early.
- Office uploads are checked as ZIP archives before parsing: member count, total uncompressed
  size, path traversal, and the presence of `[Content_Types].xml` plus `xl/workbook.xml` or
  `word/document.xml`.

## PDF generation (`conversions/pdf_render.py`)

All HTML -> PDF rendering goes through
`render_pdf(body_html, output_path, *, title, landscape, extra_css, page_size, margins)`.
`page_size`/`margins` (points) let a source document's page setup drive `@page` (docx -> pdf);
the default is A4 with 1.8 cm margins. It wraps the body in a fixed document with the base
stylesheet and calls `pisa.CreatePDF(..., resource_policy=POLICY)` where

```python
POLICY = ResourceAccessPolicy.server(base_dir=FONT_DIR, allow_remote=False, max_render_seconds=...)
```

so the renderer can read only the font directory, never the network, and never other local
files. User-supplied HTML is sanitised with `nh3` first (allow-listed tags/attributes —
`class`/`id` are allowed; inline `style` values drop declarations containing `url(`,
`expression(`, `@import`, `javascript:` and `font-family`/`font`; `<style>`, `<script>` and
`<title>` blocks removed; `http(s)` image sources dropped, `data:` images allowed and bounded
by the policy's pixel/byte limits).

### Fonts and scripts

`@font-face` registers the bundled faces: DejaVu Sans (regular/bold/oblique/bold-oblique,
DejaVu license), Droid Sans Fallback (Apache-2.0, AOSP — Han, Kana, fullwidth forms) and
Noto Sans KR (SIL OFL 1.1 — Hangul). `apply_script_fonts()` wraps text-node runs of
Han/Kana/CJK-punctuation/fullwidth characters in `.x-cjk` spans and Hangul runs in
`.x-hangul` spans so generated PDFs keep DejaVu for Latin and switch to the bundled script
fonts for CJK — authors never choose `font-family` themselves.

### Author stylesheets

For `html -> pdf` the author's `<style>` blocks are extracted before `nh3` (which strips
them), filtered by `sanitize_css()`, and appended to the base CSS. The sanitiser removes
comments, `@import`/`@namespace`/`@charset` statements, `@font-face`/`@keyframes` blocks,
and any declaration whose value contains `url(`, `expression(`, `javascript:`,
`-moz-binding`, `behavior` or a backslash, plus `font-family`/`font` — so classes, ids,
`display`, colours and `@media`/`@page` rules reach the PDF but nothing can load external
resources or override bundled fonts. The result is capped at `MAX_CSS_BYTES`.

### DOCX fidelity

`docx -> pdf/html` maps the document's own formatting onto inline styles: paragraph
alignment, indents, spacing and line-height; run size, colour, highlight, caps and
super/subscript; table cell widths, shading, vertical alignment, colspans and rowspans;
embedded images at their declared size (capped to the printable width); numbered list types
read from the numbering part; the first section's page size/orientation/margins (`@page`,
PDF only) and its header/footer text emitted once as muted blocks.

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

Render runs `gunicorn` 26.x from `render.yaml`/`Procfile` with one worker and a few threads;
the worker is mostly waiting on child processes, so threads are cheap. `--timeout` is longer
than `CONVERSION_TIMEOUT` plus upload time. Health checks hit `/health`. No secrets are
needed. The Blueprint sets `MAX_CONCURRENT_CONVERSIONS=1` and `CONVERSION_MEMORY_BYTES`
(256 MiB) for the 512 MiB instance; the cgroup clamp is what actually enforces the budget
on any container. The build command ends with `python -m conversions.ocr_models` and
`gunicorn.conf.py` repeats the check at startup in case the Blueprint build command is not
synced — only model files are fetched and verified; a failure stops the deploy before any
uploads are accepted. CI's `gunicorn-smoke` job replays the exact Procfile command on Ubuntu and asserts
real conversions succeed before a deploy can rely on them.

## Tests

- `pytest` unit and API tests run with `CONVERSION_ISOLATION=inline` for speed; `tests/test_runner.py`
  exercises `process` mode (success, timeout kill, crash isolation, busy 503, idle-worker
  lifecycle on spawn platforms).
- `tests/test_ocr.py` (marked `ocr`, in the default suite) runs the real RapidOCR engine on
  synthetic scanned pages.
- `tests/e2e` runs Playwright against a live local server (`pytest -m e2e`), covering the full
  browser flow, mobile layout, theme persistence, dialogs and keyboard access.
- CI (`.github/workflows/ci.yml`) runs ruff, the unit suite on Python 3.12 and 3.13, the e2e
  suite, `pip-audit`, and a `gunicorn-smoke` job that runs the Procfile command and asserts
  real conversions over HTTP. The smoke job additionally builds a Linux image and runs the
  service in a 512 MiB, no-swap, 1-CPU container on a dedicated bridge network;
  `scripts/smoke_service.py` then exercises every family over HTTP (including serial and
  concurrent OCR, six fresh-process scanned-PDF OCR repetitions that must each pass on the
  first attempt, and an oversized image that must return a controlled 422) and asserts
  cgroup `oom`/`oom_kill` events stay at zero, `memory.peak` keeps at least 64 MiB of
  headroom, the gunicorn master/worker never restart, and health stays stable throughout.
  Dependabot keeps pip and Actions dependencies current.
