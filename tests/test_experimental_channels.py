import threading

import pandas as pd
import pytest

from tribev2.experimental import ChannelService, EventChannel, ServiceNamespace


# ---------------------------------------------------------------------------
# EventChannel
# ---------------------------------------------------------------------------


def test_event_channel_send_and_recv() -> None:
    ch = EventChannel()
    df = pd.DataFrame({"type": ["Word"], "text": ["hello"]})
    ch.send(df)
    result = ch.recv()
    assert result is not None
    pd.testing.assert_frame_equal(result, df)


def test_event_channel_close_signals_none() -> None:
    ch = EventChannel()
    ch.close()
    assert ch.recv() is None


def test_event_channel_send_after_close_raises() -> None:
    ch = EventChannel()
    ch.close()
    with pytest.raises(RuntimeError, match="send on a closed EventChannel"):
        ch.send(pd.DataFrame())


def test_event_channel_multiple_items_then_close() -> None:
    ch = EventChannel()
    frames = [
        pd.DataFrame({"x": [i]}) for i in range(3)
    ]
    for df in frames:
        ch.send(df)
    ch.close()

    for expected in frames:
        result = ch.recv()
        assert result is not None
        pd.testing.assert_frame_equal(result, expected)

    assert ch.recv() is None


# ---------------------------------------------------------------------------
# ChannelService
# ---------------------------------------------------------------------------


def _add_flag(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    out["flag"] = True
    return out


def test_channel_service_runs_transform_via_thread() -> None:
    svc = ChannelService(name="add_flag", transform=_add_flag)
    in_chan = EventChannel()
    out_chan = EventChannel()

    df = pd.DataFrame({"type": ["Audio"]})
    in_chan.send(df)
    in_chan.close()

    thread = svc.start(in_chan, out_chan)
    result = out_chan.recv()
    assert out_chan.recv() is None  # channel was closed by service
    thread.join()

    assert result is not None
    assert result.loc[0, "flag"] == True  # noqa: E712  (np.True_ != True via `is`)


def test_channel_service_closes_output_when_input_closes() -> None:
    svc = ChannelService(name="identity", transform=lambda df: df)
    in_chan = EventChannel()
    out_chan = EventChannel()
    in_chan.close()

    thread = svc.start(in_chan, out_chan)
    assert out_chan.recv() is None
    thread.join()


# ---------------------------------------------------------------------------
# ServiceNamespace — mount / unmount / list
# ---------------------------------------------------------------------------


def test_service_namespace_mount_and_list() -> None:
    ns = ServiceNamespace()
    svc = ChannelService(name="svc", transform=lambda df: df)

    ns.mount("/normalize", svc)
    ns.mount("extract", svc)  # without leading slash

    assert ns.list_mounts() == ("/extract", "/normalize")


def test_service_namespace_get_returns_mounted_service() -> None:
    ns = ServiceNamespace()
    svc = ChannelService(name="svc", transform=lambda df: df)
    ns.mount("/normalize", svc)

    assert ns.get("/normalize") is svc
    assert ns.get("normalize") is svc  # path is normalized
    assert ns.get("/missing") is None


def test_service_namespace_unmount_removes_service() -> None:
    ns = ServiceNamespace()
    svc = ChannelService(name="svc", transform=lambda df: df)
    ns.mount("/svc", svc)
    ns.unmount("/svc")

    assert ns.get("/svc") is None
    assert ns.list_mounts() == ()


def test_service_namespace_unmount_missing_path_is_noop() -> None:
    ns = ServiceNamespace()
    ns.unmount("/nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# ServiceNamespace — compose
# ---------------------------------------------------------------------------


def _append_a(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["a"] = 1
    return out


def _append_b(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["b"] = 2
    return out


def test_service_namespace_compose_applies_transforms_in_order() -> None:
    ns = ServiceNamespace()
    ns.mount("/a", ChannelService("a", _append_a))
    ns.mount("/b", ChannelService("b", _append_b))

    pipeline = ns.compose("/a", "/b")
    result = pipeline(pd.DataFrame({"type": ["Word"]}))

    assert result.loc[0, "a"] == 1
    assert result.loc[0, "b"] == 2


def test_service_namespace_compose_raises_for_missing_mount() -> None:
    ns = ServiceNamespace()

    with pytest.raises(KeyError, match="/missing"):
        ns.compose("/missing")


# ---------------------------------------------------------------------------
# ServiceNamespace — run_pipeline (sequential)
# ---------------------------------------------------------------------------


def test_run_pipeline_sequential_applies_transforms() -> None:
    ns = ServiceNamespace()
    ns.mount("/a", ChannelService("a", _append_a))
    ns.mount("/b", ChannelService("b", _append_b))

    result = ns.run_pipeline(["/a", "/b"], pd.DataFrame({"type": ["Audio"]}))

    assert result.loc[0, "a"] == 1
    assert result.loc[0, "b"] == 2


def test_run_pipeline_sequential_does_not_mutate_input() -> None:
    ns = ServiceNamespace()
    ns.mount("/a", ChannelService("a", _append_a))

    df = pd.DataFrame({"type": ["Word"]})
    _ = ns.run_pipeline(["/a"], df)

    assert "a" not in df.columns


# ---------------------------------------------------------------------------
# ServiceNamespace — run_pipeline (threaded / channel-based)
# ---------------------------------------------------------------------------


def test_run_pipeline_threaded_applies_transforms() -> None:
    ns = ServiceNamespace()
    ns.mount("/a", ChannelService("a", _append_a))
    ns.mount("/b", ChannelService("b", _append_b))

    result = ns.run_pipeline(
        ["/a", "/b"],
        pd.DataFrame({"type": ["Audio"]}),
        threaded=True,
    )

    assert result.loc[0, "a"] == 1
    assert result.loc[0, "b"] == 2


def test_run_pipeline_threaded_raises_for_missing_mount() -> None:
    ns = ServiceNamespace()
    with pytest.raises(KeyError, match="/nope"):
        ns.run_pipeline(["/nope"], pd.DataFrame(), threaded=True)


def test_run_pipeline_threaded_runs_each_service_in_own_thread() -> None:
    """Verify that each service actually runs in a distinct thread."""
    observed_thread_ids: list[int] = []
    lock = threading.Lock()

    def recording_transform(df: pd.DataFrame) -> pd.DataFrame:
        with lock:
            observed_thread_ids.append(threading.current_thread().ident or 0)
        return df

    ns = ServiceNamespace()
    ns.mount("/s0", ChannelService("s0", recording_transform))
    ns.mount("/s1", ChannelService("s1", recording_transform))

    ns.run_pipeline(
        ["/s0", "/s1"],
        pd.DataFrame({"x": [1]}),
        threaded=True,
    )

    assert len(observed_thread_ids) == 2
    # Each service should run in its own thread (different from the test thread).
    main_tid = threading.current_thread().ident
    for tid in observed_thread_ids:
        assert tid != main_tid


def test_run_pipeline_sequential_and_threaded_give_same_result() -> None:
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["normalized"] = True
        return out

    def enrich(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["enriched"] = True
        return out

    ns = ServiceNamespace()
    ns.mount("/normalize", ChannelService("normalize", normalize))
    ns.mount("/enrich", ChannelService("enrich", enrich))

    events = pd.DataFrame({"type": ["Word", "Audio"], "start": [0.0, 1.0]})
    paths = ["/normalize", "/enrich"]

    seq_result = ns.run_pipeline(paths, events, threaded=False)
    thr_result = ns.run_pipeline(paths, events, threaded=True)

    pd.testing.assert_frame_equal(
        seq_result.reset_index(drop=True),
        thr_result.reset_index(drop=True),
    )
