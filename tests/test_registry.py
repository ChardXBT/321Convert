import pytest

import conversions
from core import registry
from core.errors import RequestValidationError


def test_every_advertised_output_has_a_converter():
    for family in registry.describe()["families"]:
        for output in family["outputs"]:
            assert (family["id"], output["ext"]) in conversions.CONVERTERS


def test_every_converter_is_advertised():
    advertised = {
        (family["id"], output["ext"])
        for family in registry.describe()["families"]
        for output in family["outputs"]
    }
    assert set(conversions.CONVERTERS) == advertised


def test_mimetypes_cover_every_output_including_zip():
    for ext, output in registry.OUTPUT_FORMATS.items():
        assert output.mimetype, ext
    assert registry.output_format("zip").mimetype == "application/zip"


def test_describe_shape():
    described = registry.describe()
    assert described["max_upload_mb"] >= 1
    assert ".heic" in described["accept"] and ".md" in described["accept"]
    image = next(f for f in described["families"] if f["id"] == "image")
    assert {"ext": "avif", "label": "AVIF"} in image["outputs"]
    assert "quality" in image["options"]


def test_quality_bounds_and_type():
    for bad in ("0", "101", "abc"):
        with pytest.raises(RequestValidationError) as info:
            registry.validate_options("image", "jpg", {"quality": bad})
        assert "Quality must be a whole number between 1 and 100." in str(info.value)


def test_blank_option_uses_default():
    assert registry.validate_options("image", "jpg", {"quality": ""}) == {"quality": 82}
    assert registry.validate_options("image", "jpg", {}) == {"quality": 82}


def test_options_not_applicable_are_dropped():
    assert registry.validate_options("image", "png", {"quality": "50"}) == {}
    assert registry.validate_options("spreadsheet", "csv", {"quality": "50"}) == {}
    assert registry.validate_options("text", "html", {"title": "Hi"}) == {"title": "Hi"}
    assert registry.validate_options("text", "pdf", {"title": "Hi"}) == {}


def test_sheet_name_truncated_and_control_chars_stripped():
    value = "A" * 150 + "\x00\x07"
    options = registry.validate_options("spreadsheet", "csv", {"sheet_name": value})
    assert options["sheet_name"] == "A" * 100


def test_stem_is_ignored_from_the_form():
    options = registry.validate_options("image", "jpg", {"_stem": "evil"})
    assert "_stem" not in options


def test_unknown_fields_ignored():
    assert registry.validate_options("image", "jpg", {"nonsense": "x"}) == {"quality": 82}
