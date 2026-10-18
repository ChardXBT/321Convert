"""Browser tests for the rebuilt UI. Opt in with ``pytest -m e2e``."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def server():
    port = _free_port()
    env = dict(os.environ)
    env.update(
        {
            "CONVERSION_ISOLATION": "inline",
            "PORT": str(port),
            "LOG_LEVEL": "WARNING",
            "RATE_LIMIT_REQUESTS": "100000",
        }
    )
    proc = subprocess.Popen(  # noqa: S603 -- launching our own dev server is the point
        [sys.executable, "app.py"],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("dev server exited during startup")
            try:
                with urllib.request.urlopen(base + "/health", timeout=1):  # noqa: S310 -- localhost only
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("dev server did not become healthy in 20s")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(10)


@pytest.fixture()
def browser_context_args(browser_context_args):
    return {**browser_context_args, "accept_downloads": True}


@pytest.fixture()
def console_errors(page):
    errors = []

    def on_console(message):
        # Chromium logs every non-2xx response as a resource error; that is
        # the conversion API doing its job, not a page bug.
        if message.type == "error" and not message.text.startswith("Failed to load resource"):
            errors.append(message.text)

    page.on("console", on_console)
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield errors
    assert errors == []


@pytest.fixture()
def sample_files(tmp_path):
    from openpyxl import Workbook
    from PIL import Image

    png_path = tmp_path / "sample.png"
    Image.new("RGB", (40, 20), (200, 30, 40)).save(png_path)

    xlsx_path = tmp_path / "book.xlsx"
    book = Workbook()
    book.active.append(["name", "value"])
    book.active.append(["a", 1])
    book.save(xlsx_path)

    txt_path = tmp_path / "note.txt"
    txt_path.write_text("hello world", encoding="utf-8")

    bad_png = tmp_path / "broken.png"
    bad_png.write_bytes(os.urandom(64))

    exe_path = tmp_path / "tool.exe"
    exe_path.write_bytes(b"MZ" + os.urandom(32))

    return {
        "png": png_path,
        "xlsx": xlsx_path,
        "txt": txt_path,
        "bad_png": bad_png,
        "exe": exe_path,
    }


def test_page_loads(server, page, console_errors):
    response = page.goto(server)
    assert "321Convert" in page.title()
    assert "Convert files in seconds." in page.locator("h1").inner_text()
    csp = response.headers.get("content-security-policy", "")
    assert "nonce-" in csp and "script-src 'self'" in csp
    assert page.locator("html").get_attribute("data-theme") in ("light", "dark")


def test_empty_state_layout(server, page, console_errors):
    page.goto(server)
    assert page.locator("#clearAll").is_hidden()
    assert page.locator("#downloadAll").is_hidden()
    sprite = page.locator("body > svg[hidden]")
    assert sprite.evaluate("node => node.getBoundingClientRect().height") == 0
    header_top = page.locator(".site-header").evaluate("node => node.getBoundingClientRect().top")
    assert header_top < 60
    sun = page.locator(".icon-sun")
    moon = page.locator(".icon-moon")
    assert sun.is_visible() != moon.is_visible()


def test_robots_txt(server, page):
    response = page.request.get(server + "/robots.txt")
    assert response.status == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "User-agent" in response.text()


def test_formats_details(server, page, console_errors):
    page.goto(server)
    details = page.locator("details.formats")
    details.locator("summary").click()
    assert details.get_attribute("open") is not None
    text = details.inner_text()
    assert "HEIC" in text and "Markdown" in text


def test_options_validation_blocks_convert(server, page, console_errors, sample_files):
    page.goto(server)
    page.set_input_files("#fileInput", str(sample_files["png"]))
    page.locator("#optMaxDimension").fill("5")
    page.click("#convertAll")
    assert page.locator("#optMaxDimension").evaluate("node => node.matches(':invalid')")
    page.wait_for_timeout(300)
    assert page.locator(".file-row").get_attribute("data-status") == "ready"
    assert page.locator("a.download-button").count() == 0


def test_single_conversion(server, page, console_errors, sample_files):
    page.goto(server)
    page.set_input_files("#fileInput", str(sample_files["png"]))
    row = page.locator(".file-row").first
    assert row.locator(".badge").inner_text() == "PNG"
    assert row.locator("select").input_value() == "jpg"

    page.click("#convertAll")
    row.locator("a.download-button").wait_for()
    with page.expect_download() as info:
        row.locator("a.download-button").click()
    download = info.value
    assert download.suggested_filename == "sample.jpg"
    assert download.path().read_bytes()[:2] == b"\xff\xd8"
    assert "1 converted" in page.locator("#summary").inner_text()


def test_multiple_conversions(server, page, console_errors, sample_files):
    page.goto(server)
    page.set_input_files(
        "#fileInput",
        [str(sample_files["png"]), str(sample_files["xlsx"]), str(sample_files["txt"])],
    )
    assert page.locator(".file-row").count() == 3
    assert not page.locator("#options").is_hidden()
    assert not page.locator("#fieldQuality").is_hidden()
    assert not page.locator("#fieldSheetName").is_hidden()
    assert page.locator(".file-row").nth(2).locator("select").input_value() == "pdf"

    page.click("#convertAll")
    page.locator("a.download-button").nth(2).wait_for()
    assert page.locator("a.download-button").count() == 3
    assert "3 converted" in page.locator("#summary").inner_text()
    assert page.locator("#downloadAll").is_visible()


def test_failed_row_retries_and_summary(server, page, console_errors, sample_files):
    page.goto(server)
    page.set_input_files("#fileInput", [str(sample_files["bad_png"]), str(sample_files["png"])])
    page.click("#convertAll")
    page.locator("a.download-button").wait_for()
    bad_row = page.locator(".file-row").first
    assert "could not be read" in bad_row.locator(".file-error").inner_text()
    assert bad_row.locator(".retry-button").is_visible()
    assert "1 converted · 1 failed" in page.locator("#summary").inner_text()


def test_unsupported_file_disables_convert(server, page, console_errors, sample_files):
    page.goto(server)
    page.set_input_files("#fileInput", str(sample_files["exe"]))
    assert "Unsupported file type" in page.locator(".file-row .file-meta").inner_text()
    assert page.locator("#convertAll").is_disabled()
    page.set_input_files("#fileInput", str(sample_files["png"]))
    assert page.locator("#convertAll").is_enabled()


def test_options_follow_targets(server, page, console_errors, sample_files):
    page.goto(server)
    page.set_input_files("#fileInput", str(sample_files["png"]))
    select = page.locator(".file-row select")
    select.select_option("png")
    assert page.locator("#fieldQuality").is_hidden()
    assert not page.locator("#fieldMaxDimension").is_hidden()
    select.select_option("webp")
    assert not page.locator("#fieldQuality").is_hidden()


def test_theme_toggle_persists(server, page, console_errors):
    page.goto(server)
    page.click("#themeToggle")
    assert page.locator("html").get_attribute("data-theme") == "dark"
    assert page.evaluate("localStorage.getItem('theme')") == "dark"
    assert page.locator("#themeToggle").get_attribute("aria-pressed") == "true"
    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "dark"


@pytest.mark.parametrize("size", [(390, 844), (360, 780)])
def test_mobile_no_horizontal_overflow(server, page, console_errors, sample_files, size):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(server)
    fits = "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    assert page.evaluate(fits)
    page.set_input_files("#fileInput", [str(sample_files["png"]), str(sample_files["txt"])])
    assert page.evaluate(fits)
    box = page.locator("#convertAll").bounding_box()
    assert box["height"] >= 40


def test_keyboard_reaches_drop_zone(server, page, console_errors):
    page.goto(server)
    page.locator("body").click(position={"x": 5, "y": 5})
    for _ in range(8):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.id") == "dropZone":
            break
    assert page.evaluate("document.activeElement.id") == "dropZone"
    with page.expect_file_chooser():
        page.keyboard.press("Enter")


def test_dialogs_open_and_close(server, page, console_errors):
    page.goto(server)
    page.click("text=Terms")
    assert page.locator("#termsDialog").is_visible()
    page.keyboard.press("Escape")
    assert not page.locator("#termsDialog").is_visible()
    page.click("text=MIT License")
    assert page.locator("#licenseDialog").is_visible()
    page.locator("#licenseDialog [data-dialog-close]").click()
    assert not page.locator("#licenseDialog").is_visible()


def test_remove_and_clear_all(server, page, console_errors, sample_files):
    page.goto(server)
    assert page.locator("#dropZone").is_visible()
    page.set_input_files("#fileInput", [str(sample_files["png"]), str(sample_files["txt"])])
    assert page.locator(".file-row").count() == 2
    assert page.locator("#dropZone").is_hidden()
    assert page.locator("#addMore").is_visible()
    page.locator(".file-row .remove").first.click()
    assert page.locator(".file-row").count() == 1
    page.click("#clearAll")
    assert page.locator(".file-row").count() == 0
    assert page.locator("#dropZone").is_visible()
    assert page.locator("#addMore").is_hidden()
    assert page.locator("#options").is_hidden()
