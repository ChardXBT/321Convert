# 321Convert

A privacy-first Flask file converter deployed on Render.

**Live demo:** [three21convert.onrender.com](https://three21convert.onrender.com)

Maintained by [ChardXBT](https://github.com/ChardXBT).

## Privacy model

- Files are processed inside a unique operating-system temporary directory.
- Results are returned directly in the conversion request as private attachments.
- Temporary input and output files are deleted before the response is sent.
- There are no public download URLs, accounts, databases, analytics, or permanent uploads.

No hosted service can honestly promise to be "unhackable." This project reduces risk with strict conversion allowlists, bounded uploads and outputs, archive-bomb checks, image decompression-bomb protection, rate limiting, sanitized errors, security headers, and a strict Content Security Policy.

## Supported conversions

- Images: JPG, PNG, WebP, GIF, BMP, and TIFF
- PDF to DOCX text extraction
- XLSX to PDF or CSV
- HTML to PDF as inert text
- TXT to escaped HTML

DOCX to PDF and OCR are intentionally not advertised because they require system software that is not available on a standard Render Python service.

## Local setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Tests

```powershell
python -m unittest discover -v
python -m pip check
```

## Render deployment

The repository includes `render.yaml` and a hardened `Procfile`. Connect the public GitHub repository to Render and deploy the Blueprint. Do not add secrets: the app does not require any.

Useful environment controls:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `MAX_UPLOAD_BYTES` | 26214400 | Maximum request size |
| `MAX_OUTPUT_BYTES` | 78643200 | Maximum returned file size |
| `MAX_ARCHIVE_BYTES` | 104857600 | Maximum expanded Office archive size |
| `RATE_LIMIT_REQUESTS` | 20 | Requests allowed per window |
| `RATE_LIMIT_WINDOW` | 600 | Rate-limit window in seconds |
| `TRUST_PROXY` | false locally, true on Render | Trust one known proxy hop |

## License

MIT

## Legal

- [Terms of Service](TERMS.md)
- [MIT License](LICENSE)
