import re
from fastapi import HTTPException

BUILD_LEN = 12
BUILD_REGEX = re.compile(r"^[0-9a-z]{12}$")

# Allows lowercase alphanumeric and hyphens, 1-64 chars, no leading/trailing hyphens
SAFE_ID_REGEX = re.compile(r"^[a-z0-9]([a-z0-9\-]{0,62}[a-z0-9])?$")


def validate_build_string(build: str) -> str:
    """
    Garante que a build_string é segura e válida.
    Retorna a própria build se OK.
    Lança HTTP 400 se inválida.
    """

    if not isinstance(build, str):
        raise HTTPException(status_code=400, detail="Build inválida")

    if len(build) != BUILD_LEN:
        raise HTTPException(status_code=400, detail="Build inválida")

    if not BUILD_REGEX.match(build):
        raise HTTPException(status_code=400, detail="Build inválida")

    return build


def validate_safe_id(value: str, field_name: str) -> str:
    """
    Validates that an identifier (client_id, scene_id) is safe for use in
    file paths and URLs. Prevents path traversal attacks.

    Format: lowercase letters (a-z), digits (0-9), and hyphens (-).
    Length: 1-64 characters. Must not start or end with a hyphen.

    Raises HTTP 400 if invalid.
    """
    if not isinstance(value, str) or not value:
        raise HTTPException(status_code=400, detail=f"{field_name} inválido")

    if ".." in value or "/" in value or "\\" in value:
        raise HTTPException(status_code=400, detail=f"{field_name} contém caracteres proibidos")

    if not SAFE_ID_REGEX.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} deve conter apenas letras minúsculas, números e hífens",
        )

    return value
