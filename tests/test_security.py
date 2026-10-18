import io
import re
import tempfile
from pathlib import Path

import app as app_module
from core import config
from tests import samples


def test_home_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "object-src 'none'" in csp
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


def test_csp_nonce_matches_html(client):
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]
    match = re.search(r"'nonce-([^']+)'", csp)
    assert match
    assert match.group(1).encode() in response.data


def test_hsts_only_when_secure(client):
    secure = client.get("/", base_url="https://example.test")
    plain = client.get("/", base_url="http://localhost")
    assert "Strict-Transport-Security" in secure.headers
    assert "Strict-Transport-Security" not in plain.headers


def test_static_cache_headers(client):
    versioned = client.get("/static/app.js?v=abc123")
    plain = client.get("/static/app.js")
    assert "immutable" in versioned.headers["Cache-Control"]
    assert "31536000" in versioned.headers["Cache-Control"]
    assert plain.headers["Cache-Control"] == "public, max-age=3600"


def test_cross_origin_post_rejected(client):
    response = client.post(
        "/api/convert",
        headers={"Origin": "https://attacker.example"},
        data={"file": (samples.png(), "x.png"), "target": "jpg"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 403


def test_sec_fetch_site_cross_site_rejected(client):
    response = client.post(
        "/api/convert",
        headers={"Sec-Fetch-Site": "cross-site"},
        data={"file": (samples.png(), "x.png"), "target": "jpg"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 403


def test_same_origin_allowed(client):
    response = client.post(
        "/api/convert",
        headers={"Origin": "http://localhost"},
        data={"file": (samples.png(), "x.png"), "target": "jpg"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 1)
    first = client.post("/api/convert", data={"target": "jpg"})
    second = client.post("/api/convert", data={"target": "jpg"})
    assert first.status_code == 400
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1


def test_rate_limit_map_full_does_not_evict_active(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_WINDOW", 600)
    for number in range(10_000):
        app_module.rate_limit_hits[f"client-{number}"].append(float("inf"))
    with app_module.app.test_request_context("/", environ_base={"REMOTE_ADDR": "new-client"}):
        limited, _retry = app_module._rate_limited()
    assert limited is True
    assert len(app_module.rate_limit_hits) == 10_000


def test_oversized_request_413(client, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "MAX_CONTENT_LENGTH", 32)
    response = client.post(
        "/api/convert",
        data={"file": (io.BytesIO(b"x" * 200), "big.png"), "target": "jpg"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 413


def test_zip_slip_xlsx_rejected(client):
    response = samples.convert(client, "u.xlsx", samples.zip_slip_xlsx(), "csv")
    assert response.status_code == 400
    assert b"unsafe archive paths" in response.data


def test_not_office_zip_rejected(client):
    response = samples.convert(client, "u.xlsx", samples.zip_not_office(), "csv")
    assert response.status_code == 400
    assert b"not a valid Excel workbook" in response.data


def test_archive_bomb_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_ARCHIVE_BYTES", 100)
    response = samples.convert(client, "d.xlsx", samples.xlsx(), "csv")
    assert response.status_code == 400
    assert b"processing limit" in response.data


def test_damaged_pdf_no_parser_leak(client, caplog):
    with caplog.at_level("WARNING", logger="app"):
        response = samples.convert(client, "damaged.pdf", io.BytesIO(b"%PDF-secret parser detail"), "txt")
    assert response.status_code == 422
    assert b"secret parser detail" not in response.data
    assert b"could not be converted" in response.data or b"could not be opened" in response.data
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "damaged.pdf" not in logs
    assert "secret parser detail" not in logs


def test_unknown_target_400(client):
    response = samples.convert(client, "x.png", samples.png(), "xyz")
    assert response.status_code == 400


def test_no_temp_dirs_left(client):
    tempdir = Path(tempfile.gettempdir())
    before = set(tempdir.glob("321convert-*"))
    response = samples.convert(client, "x.png", samples.png(), "jpg")
    assert response.status_code == 200
    assert set(tempdir.glob("321convert-*")) == before


def test_old_public_routes_gone(client):
    assert client.get("/downloads/secret.txt").status_code == 404
    assert client.get("/previews/secret.txt").status_code == 404
