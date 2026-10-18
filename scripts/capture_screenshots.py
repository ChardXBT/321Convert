"""Capture documentation screenshots of the running app.

Usage:
    python scripts/capture_screenshots.py [--base-url http://127.0.0.1:5000]

Writes PNGs into docs/screenshots/. Builds its own synthetic upload files, so
it works against any running instance (local dev server or production).
"""

import argparse
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "screenshots"


def build_files(directory: Path) -> dict:
    from openpyxl import Workbook
    from PIL import Image

    png_path = directory / "sample.png"
    Image.new("RGB", (800, 450), (196, 81, 27)).save(png_path)

    xlsx_path = directory / "supplies.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Supplies"
    sheet.append(["item", "quantity", "price"])
    for row in (["Pencils", 40, 0.5], ["Notebooks", 12, 2.75], ["Labels", 200, 0.08]):
        sheet.append(row)
    book.save(xlsx_path)

    return {"png": png_path, "xlsx": xlsx_path}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp:
        files = build_files(Path(temp))
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1440, "height": 900},
            )
            page = context.new_page()
            page.goto(args.base_url, wait_until="networkidle")

            page.screenshot(path=OUT / "desktop-empty.png")

            page.set_input_files("#fileInput", [str(files["png"]), str(files["xlsx"])])
            rows = page.locator(".file-row")
            rows.nth(0).locator("select").select_option("webp")
            page.click("#convertAll")
            page.locator("a.download-button").nth(1).wait_for(state="visible")
            page.screenshot(path=OUT / "desktop-results.png")

            page.click("#themeToggle")
            page.wait_for_timeout(400)
            page.screenshot(path=OUT / "desktop-dark.png")
            context.close()

            mobile = browser.new_context(
                accept_downloads=True,
                viewport={"width": 390, "height": 844},
            )
            mpage = mobile.new_page()
            mpage.goto(args.base_url, wait_until="networkidle")
            mpage.set_input_files("#fileInput", str(files["png"]))
            mpage.screenshot(path=OUT / "mobile.png", full_page=True)
            mobile.close()

            browser.close()

    for path in sorted(OUT.glob("*.png")):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
