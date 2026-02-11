import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.utils.build import build_key_from_indexes, validate_build


def test_build_is_deterministic_base36():
    first = build_key_from_indexes(0, [1, 2, 3])
    second = build_key_from_indexes(0, [1, 2, 3])
    assert first == second
    assert validate_build(first)


def test_build_validation_rejects_invalid_chars():
    assert not validate_build("ABC+")
    assert validate_build("abc123")
