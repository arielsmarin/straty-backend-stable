import re

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
BUILD_PATTERN = re.compile(r"^[0-9a-z]+$")


def to_base36(value: int) -> str:
    if value < 0:
        raise ValueError("negative values not supported")
    if value == 0:
        return "0"
    chars: list[str] = []
    while value:
        value, rem = divmod(value, 36)
        chars.append(ALPHABET[rem])
    return "".join(reversed(chars))


def build_key_from_indexes(scene_index: int, layer_indexes: list[int]) -> str:
    accumulator = scene_index * 97
    for idx in layer_indexes:
        accumulator = accumulator * 131 + idx
    return to_base36(accumulator)


def validate_build(value: str) -> bool:
    return bool(BUILD_PATTERN.match(value))
