import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable, Optional

_DEFAULT_UPLOAD_WORKERS = min(8, (os.cpu_count() or 4) * 2)


class TileUploadQueue:
    def __init__(
        self,
        tile_root: str,
        upload_fn: Callable[[str, str, str], None],
        workers: int = _DEFAULT_UPLOAD_WORKERS,
        on_state_change: Optional[Callable[[str, str, int], None]] = None,
    ):
        self.tile_root = tile_root
        self.upload_fn = upload_fn
        self.workers = max(1, workers)
        self._executor: ThreadPoolExecutor | None = None
        self._futures: list[Future] = []
        self._futures_lock = threading.Lock()
        self._backpressure = threading.Semaphore(256)
        self._closed = False
        self._closed_lock = threading.Lock()

        self._states: dict[str, str] = {}
        self._states_lock = threading.Lock()

        self._uploaded_count = 0
        self._uploaded_count_lock = threading.Lock()

        self._errors: list[Exception] = []
        self._errors_lock = threading.Lock()
        self._on_state_change = on_state_change

    def _set_state(self, filename: str, state: str):
        with self._states_lock:
            self._states[filename] = state

    def _emit_state(self, filename: str, state: str, lod: int):
        if self._on_state_change is None:
            return
        try:
            self._on_state_change(filename, state, lod)
        except Exception:
            logging.exception("❌ Falha no callback de estado do tile %s", filename)

    def _upload_tile(self, file_path: Path, filename: str, lod: int):
        """Upload a single tile to storage and remove the local file."""
        try:
            key = f"{self.tile_root}/{filename}"
            logging.info("⬆️ upload started: %s", filename)
            self.upload_fn(str(file_path), key, "image/jpeg")
            logging.info("✅ upload completed: %s", filename)
            self._set_state(filename, "visible")
            self._emit_state(filename, "visible", lod)
            with self._uploaded_count_lock:
                self._uploaded_count += 1
        except Exception as exc:
            with self._errors_lock:
                self._errors.append(exc)
            logging.exception("❌ Falha no upload do tile %s", filename)
        finally:
            try:
                fp = Path(file_path) if not isinstance(file_path, Path) else file_path
                if fp.exists():
                    fp.unlink()
                    logging.info("🗑️ local file removed: %s", filename)
            except OSError:
                pass
            self._backpressure.release()

    def enqueue(self, file_path: Path, filename: str, lod: int):
        self._set_state(filename, "generated")
        self._emit_state(filename, "generated", lod)
        logging.info("🧩 tile generated: %s", filename)
        self._backpressure.acquire()
        logging.info("📋 upload queued: %s", filename)
        future = self._executor.submit(self._upload_tile, file_path, filename, lod)
        with self._futures_lock:
            self._futures.append(future)

    def start(self):
        self._executor = ThreadPoolExecutor(
            max_workers=self.workers,
            thread_name_prefix="tile-upload",
        )

    def close_and_wait(self):
        with self._closed_lock:
            if self._closed:
                return
            self._closed = True

        with self._futures_lock:
            pending = list(self._futures)

        wait(pending)

        if self._executor:
            self._executor.shutdown(wait=True)

        with self._errors_lock:
            if self._errors:
                raise RuntimeError(f"Falha em {len(self._errors)} uploads de tile")

    @property
    def uploaded_count(self) -> int:
        with self._uploaded_count_lock:
            return self._uploaded_count

    @property
    def states(self) -> dict[str, str]:
        with self._states_lock:
            return dict(self._states)
