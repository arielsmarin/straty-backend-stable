import re
from fastapi import HTTPException

BUILD_LEN = 12
BUILD_REGEX = re.compile(r"^[0-9a-z]{12}$")


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
