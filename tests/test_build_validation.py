import pytest
from fastapi import HTTPException

from utils.build_validation import (
    validate_build_string,
    validate_safe_id,
)


class TestValidateBuildString:
    def test_valid_build_string(self):
        assert validate_build_string("0a1b2c3d4e5f") == "0a1b2c3d4e5f"

    def test_valid_all_zeros(self):
        assert validate_build_string("000000000000") == "000000000000"

    def test_invalid_too_short(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_build_string("abc")
        assert exc_info.value.status_code == 400

    def test_invalid_too_long(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_build_string("0000000000000")
        assert exc_info.value.status_code == 400

    def test_invalid_uppercase(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_build_string("0A1B2C3D4E5F")
        assert exc_info.value.status_code == 400

    def test_invalid_special_chars(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_build_string("../../../etc")
        assert exc_info.value.status_code == 400

    def test_invalid_not_string(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_build_string(12345)
        assert exc_info.value.status_code == 400


class TestValidateSafeId:
    def test_valid_simple_id(self):
        assert validate_safe_id("monte-negro", "client") == "monte-negro"

    def test_valid_alphanumeric(self):
        assert validate_safe_id("client123", "client") == "client123"

    def test_valid_single_char(self):
        assert validate_safe_id("a", "client") == "a"

    def test_path_traversal_dotdot(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("../../../etc", "client")
        assert exc_info.value.status_code == 400

    def test_path_traversal_slash(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("client/../../passwd", "client")
        assert exc_info.value.status_code == 400

    def test_path_traversal_backslash(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("client\\..\\..\\passwd", "client")
        assert exc_info.value.status_code == 400

    def test_empty_string(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("", "client")
        assert exc_info.value.status_code == 400

    def test_none_value(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id(None, "client")
        assert exc_info.value.status_code == 400

    def test_uppercase_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("Monte-Negro", "client")
        assert exc_info.value.status_code == 400

    def test_leading_hyphen_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("-monte", "client")
        assert exc_info.value.status_code == 400

    def test_trailing_hyphen_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("monte-", "client")
        assert exc_info.value.status_code == 400

    def test_spaces_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("monte negro", "client")
        assert exc_info.value.status_code == 400

    def test_special_chars_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_safe_id("client@#$", "client")
        assert exc_info.value.status_code == 400
