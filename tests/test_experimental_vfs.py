import pandas as pd
import pytest

from tribev2.experimental import EventNamespaceFS


def test_event_namespace_fs_writes_and_reads_virtual_files(tmp_path) -> None:
    fs = EventNamespaceFS(root=tmp_path)
    input_path = fs.write_input_text("request.txt", "predict this")
    events_path = fs.write_events(
        pd.DataFrame([{"type": "Word", "text": "hello", "start": 0.0, "duration": 1.0}])
    )
    output_path = fs.write_output_json("prediction.json", {"segments": 1})
    feature_path = fs.write_cached_feature_bytes("audio/0.bin", b"abc")

    assert input_path == "/inputs/request.txt"
    assert events_path == "/events/events.jsonl"
    assert output_path == "/outputs/prediction.json"
    assert feature_path == "/cache/features/audio/0.bin"

    assert fs.read_text("/inputs/request.txt") == "predict this"
    assert fs.read_bytes("/cache/features/audio/0.bin") == b"abc"
    assert set(fs.list_virtual_paths()) == {
        "/inputs/request.txt",
        "/events/events.jsonl",
        "/outputs/prediction.json",
        "/cache/features/audio/0.bin",
    }


def test_event_namespace_fs_rejects_path_traversal(tmp_path) -> None:
    fs = EventNamespaceFS(root=tmp_path)

    with pytest.raises(ValueError, match="Path traversal is not allowed"):
        fs.write_input_text("../escape.txt", "nope")
