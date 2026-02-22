from storage.storage_local import append_jsonl, read_jsonl_slice


def test_append_and_read_jsonl_slice(tmp_path, monkeypatch):
    from storage import storage_local

    monkeypatch.setattr(storage_local, "ASSETS_ROOT", tmp_path)

    key = "clients/a/cubemap/s/tiles/b/tile_events.ndjson"
    append_jsonl(key, {"id": 1})
    append_jsonl(key, {"id": 2})

    events, cursor = read_jsonl_slice(key, cursor=0, limit=10)
    assert events == [{"id": 1}, {"id": 2}]
    assert cursor == 2

    events2, cursor2 = read_jsonl_slice(key, cursor=1, limit=10)
    assert events2 == [{"id": 2}]
    assert cursor2 == 2
