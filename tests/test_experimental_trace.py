import pandas as pd
import pytest

from tribev2.experimental import (
    RewriteTraceRecord,
    TraceStore,
    create_trace_record,
    default_rewriter,
    deserialize_trace,
    load_trace,
    save_trace,
    serialize_trace,
)


def test_create_trace_record_captures_digests_and_rules() -> None:
    input_events = pd.DataFrame({"type": ["Word"], "text": ["hello"]})
    output_events = pd.DataFrame({"type": ["Word"], "text": ["hello"], "flag": [True]})
    applied_rules = ("rule_a", "rule_b")

    record = create_trace_record(input_events, output_events, applied_rules)

    assert record.applied_rules == ("rule_a", "rule_b")
    assert "rows=1" in record.input_events_digest
    assert "rows=1" in record.output_events_digest
    assert record.timestamp  # non-empty ISO timestamp


def test_create_trace_record_includes_metadata_when_provided() -> None:
    events = pd.DataFrame({"type": ["Audio"]})
    record = create_trace_record(
        events, events, ("rule",), metadata={"version": "1.0"}
    )

    assert record.metadata == {"version": "1.0"}


def test_serialize_and_deserialize_trace_roundtrips() -> None:
    events = pd.DataFrame({"type": ["Word"], "text": ["test"]})
    original = create_trace_record(events, events, ("rule_x",))

    json_text = serialize_trace(original)
    restored = deserialize_trace(json_text)

    assert restored == original
    assert restored.applied_rules == ("rule_x",)


def test_save_and_load_trace_roundtrips(tmp_path) -> None:
    events = pd.DataFrame({"type": ["Audio"]})
    record = create_trace_record(events, events, ("step_1", "step_2"))

    path = save_trace(record, tmp_path / "trace.json")
    loaded = load_trace(path)

    assert loaded == record
    assert loaded.applied_rules == ("step_1", "step_2")


def test_trace_store_saves_and_lists_traces(tmp_path) -> None:
    store = TraceStore(root=tmp_path / "traces")
    events = pd.DataFrame({"type": ["Word"], "text": ["a"]})

    path1 = store.save(events, events, ("r1",), name="trace_001")
    path2 = store.save(events, events, ("r2",), name="trace_002")

    traces = store.list_traces()
    assert len(traces) == 2
    assert path1 in traces
    assert path2 in traces


def test_trace_store_load_all_returns_all_records(tmp_path) -> None:
    store = TraceStore(root=tmp_path / "traces")
    events = pd.DataFrame({"type": ["Audio"]})

    store.save(events, events, ("first",), name="a")
    store.save(events, events, ("second",), name="b")

    records = store.load_all()
    rules = {r.applied_rules for r in records}

    assert len(records) == 2
    assert ("first",) in rules
    assert ("second",) in rules


def test_trace_store_auto_names_with_timestamp(tmp_path) -> None:
    store = TraceStore(root=tmp_path / "traces")
    events = pd.DataFrame({"type": ["Word"]})

    path = store.save(events, events, ("rule",))

    assert path.suffix == ".json"
    assert path.exists()


def test_trace_record_with_rewriter_integration(tmp_path) -> None:
    """Verify trace serialization works with actual rewriter output."""
    events = pd.DataFrame(
        {
            "type": ["Word"],
            "text": ["  hello   world  "],
            "start": [0.0],
            "duration": [1.0],
        }
    )
    rewriter = default_rewriter()
    output, trace = rewriter.rewrite_with_trace(events)

    store = TraceStore(root=tmp_path)
    path = store.save(events, output, trace, name="rewriter_run")

    loaded = load_trace(path)
    assert loaded.applied_rules == trace
    assert "rows=1" in loaded.input_events_digest
