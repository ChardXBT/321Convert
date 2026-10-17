# Screenshot capture notes

Captured from [the production app](https://three21convert.onrender.com) on October 16, 2026 (America/Toronto). The Render service was allowed to wake before capture. No authentication was required.

All images show the actual deployed interface. Example uploads contain synthetic data. Screenshots have no added interface elements or retouched content. JPEG files keep the documentation small while preserving readable text.

| File | State |
| --- | --- |
| `desktop-image-converter.jpg` | Default Image tab, formats, quality, and upload limit. |
| `desktop-image-result.jpg` | Successful PNG to WebP conversion, quality 82, preview, and download. |
| `desktop-spreadsheet-result.jpg` | Successful XLSX to CSV conversion using the `Supplies` sheet. |
| `desktop-text-result.jpg` | Successful TXT to HTML conversion with a custom title, in dark theme. |
| `mobile-image-converter.jpg` | Full page at a 390 × 844 CSS-pixel viewport. This is a browser viewport check, not a physical-device test. |
| `desktop-validation-error.jpg` | Inline error after selecting a nonexistent worksheet. |

## Live verification

- PNG to WebP: downloaded image opened as WebP at the original 800 × 450 dimensions.
- XLSX to CSV: downloaded rows matched the selected `Supplies` worksheet.
- TXT to HTML: downloaded document contained the requested title and escaped text.
- PDF to DOCX: downloaded Word document contained the source PDF text under a page heading.
- HTML to PDF: downloaded PDF contained the literal HTML source as safe text.
- XLSX to PDF: downloaded PDF contained the worksheet table.
- Missing worksheet: a general inline conversion error appeared and the form remained usable.
- Terms and MIT License dialogs opened and closed. Light and dark themes were checked. The mobile page had no horizontal overflow at 390 CSS pixels.

The screenshots cover distinct workflows rather than repeating the same download state for every document format. The main README lists every available conversion and its limits. Source review informed implementation and privacy descriptions; screenshots alone do not prove server-side cleanup or security properties.
