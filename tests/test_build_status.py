"""Tests for BUILD_STATUS tracking and the /api/status/{build_id} endpoint."""

import threading


def test_build_status_dict_structure():
    """BUILD_STATUS entries have expected keys."""
    from api.server import BUILD_STATUS, BUILD_STATUS_LOCK

    build_id = "ab0000000000"
    with BUILD_STATUS_LOCK:
        BUILD_STATUS[build_id] = {"status": "processing", "lod_ready": 0}

    with BUILD_STATUS_LOCK:
        entry = BUILD_STATUS[build_id]

    assert entry["status"] == "processing"
    assert entry["lod_ready"] == 0

    # cleanup
    with BUILD_STATUS_LOCK:
        BUILD_STATUS.pop(build_id, None)


def test_build_status_lod_ready_update():
    """lod_ready updates progressively."""
    from api.server import BUILD_STATUS, BUILD_STATUS_LOCK

    build_id = "cd0000000000"
    with BUILD_STATUS_LOCK:
        BUILD_STATUS[build_id] = {"status": "processing", "lod_ready": 0}

    # Simulate LOD1 complete
    with BUILD_STATUS_LOCK:
        BUILD_STATUS[build_id]["lod_ready"] = 1

    with BUILD_STATUS_LOCK:
        assert BUILD_STATUS[build_id]["lod_ready"] == 1

    # Simulate LOD1 complete
    with BUILD_STATUS_LOCK:
        BUILD_STATUS[build_id]["lod_ready"] = 1
        BUILD_STATUS[build_id]["status"] = "completed"

    with BUILD_STATUS_LOCK:
        assert BUILD_STATUS[build_id]["lod_ready"] == 1
        assert BUILD_STATUS[build_id]["status"] == "completed"

    # cleanup
    with BUILD_STATUS_LOCK:
        BUILD_STATUS.pop(build_id, None)


def test_build_status_thread_safety():
    """BUILD_STATUS is safe for concurrent access."""
    from api.server import BUILD_STATUS, BUILD_STATUS_LOCK

    build_id = "ef0000000000"
    with BUILD_STATUS_LOCK:
        BUILD_STATUS[build_id] = {"status": "processing", "lod_ready": 0}

    errors = []

    def updater(lod):
        try:
            with BUILD_STATUS_LOCK:
                if BUILD_STATUS[build_id]["lod_ready"] < lod:
                    BUILD_STATUS[build_id]["lod_ready"] = lod
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=updater, args=(i,)) for i in range(1, 4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    with BUILD_STATUS_LOCK:
        assert BUILD_STATUS[build_id]["lod_ready"] == 3

    # cleanup
    with BUILD_STATUS_LOCK:
        BUILD_STATUS.pop(build_id, None)
