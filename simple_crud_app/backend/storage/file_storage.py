import asyncio
from collections import defaultdict
from pathlib import Path


class FileStorage:
    async def exists(self, path: str) -> bool:
        if not path:
            return False
        return await asyncio.to_thread(Path(path).exists)


class BuildLockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def get_lock(self, key: str) -> asyncio.Lock:
        return self._locks[key]
