import logging
import queue
import threading
from pathlib import Path
from typing import Callable, Optional


class TileUploadQueue:
    def __init__(
        self,
        tile_root: str,
        upload_fn: Callable[[str, str, str], None],
        workers: int = 4,
        on_state_change: Optional[Callable[[str, str, int], None]] = None,
    ):
        self.tile_root = tile_root
        self.upload_fn = upload_fn
        self.workers = max(1, workers)
        self._queue: queue.Queue[tuple[Path, str, int] | None] = queue.Queue(maxsize=256)
        self._threads: list[threading.Thread] = []
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

    def enqueue(self, file_path: Path, filename: str, lod: int):
        _ = lod
        self._set_state(filename, "generated")
        self._emit_state(filename, "generated", lod)
        self._queue.put((file_path, filename, lod))

    def _worker(self):
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return

            file_path, filename, _lod = item
            try:
                key = f"{self.tile_root}/{filename}"
                self.upload_fn(str(file_path), key, "image/jpeg")
                self._set_state(filename, "visible")
                self._emit_state(filename, "visible", _lod)
                with self._uploaded_count_lock:
                    self._uploaded_count += 1
            except Exception as exc:
                with self._errors_lock:
                    self._errors.append(exc)
                logging.exception("❌ Falha no upload do tile %s", filename)
            finally:
                # Delete local temp file immediately after upload to free disk
                try:
                    fp = Path(file_path) if not isinstance(file_path, Path) else file_path
                    if fp.exists():
                        fp.unlink()
                except OSError:
                    pass
                self._queue.task_done()

    def start(self):
        for idx in range(self.workers):
            th = threading.Thread(target=self._worker, name=f"tile-upload-{idx}", daemon=True)
            th.start()
            self._threads.append(th)

    def close_and_wait(self):
        with self._closed_lock:
            if self._closed:
                return
            self._closed = True

        for _ in range(self.workers):
            self._queue.put(None)

        self._queue.join()

        for th in self._threads:
            th.join(timeout=5)

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
