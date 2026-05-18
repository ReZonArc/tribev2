import threading
import time

import pandas as pd
import pytest

from tribev2.experimental import (
    ChannelClient,
    ChannelServer,
    RemoteChannelService,
    ServiceNamespace,
    run_remote_pipeline,
)


def _add_processed_flag(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    out["processed"] = True
    return out


def _double_value(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    if "value" in out.columns:
        out["value"] = out["value"] * 2
    return out


# ---------------------------------------------------------------------------
# ChannelServer + ChannelClient
# ---------------------------------------------------------------------------


def test_channel_server_starts_and_stops() -> None:
    server = ChannelServer(transform=_add_processed_flag)
    host, port = server.start()

    assert host == "127.0.0.1"
    assert port > 0
    assert server.bound_address == (host, port)

    server.stop()
    assert server._server_socket is None


def test_channel_client_sends_and_receives() -> None:
    server = ChannelServer(transform=_add_processed_flag)
    host, port = server.start()

    try:
        client = ChannelClient(host=host, port=port)
        client.connect()

        events = pd.DataFrame({"type": ["Word"], "text": ["hello"]})
        result = client.send(events)

        assert result is not None
        assert result.loc[0, "processed"] == True  # noqa: E712
        assert result.loc[0, "type"] == "Word"

        client.close()
    finally:
        server.stop()


def test_channel_client_multiple_requests() -> None:
    server = ChannelServer(transform=_double_value)
    host, port = server.start()

    try:
        client = ChannelClient(host=host, port=port)
        client.connect()

        for i in range(3):
            events = pd.DataFrame({"value": [i + 1]})
            result = client.send(events)
            assert result.loc[0, "value"] == (i + 1) * 2

        client.close()
    finally:
        server.stop()


def test_channel_client_not_connected_raises() -> None:
    client = ChannelClient(host="127.0.0.1", port=9999)
    with pytest.raises(RuntimeError, match="not connected"):
        client.send(pd.DataFrame())


# ---------------------------------------------------------------------------
# RemoteChannelService
# ---------------------------------------------------------------------------


def test_remote_channel_service_transform_delegates_to_server() -> None:
    server = ChannelServer(transform=_add_processed_flag)
    host, port = server.start()

    try:
        remote_svc = RemoteChannelService(name="remote", host=host, port=port)
        transform = remote_svc.transform

        events = pd.DataFrame({"type": ["Audio"]})
        result = transform(events)

        assert result.loc[0, "processed"] == True  # noqa: E712
    finally:
        server.stop()


def test_remote_channel_service_works_with_namespace() -> None:
    server = ChannelServer(transform=_add_processed_flag)
    host, port = server.start()

    try:
        remote_svc = RemoteChannelService(name="remote_proc", host=host, port=port)

        # Create a ChannelService-like wrapper for the namespace
        from tribev2.experimental import ChannelService

        local_svc = ChannelService(name="local_wrapper", transform=remote_svc.transform)

        ns = ServiceNamespace()
        ns.mount("/remote", local_svc)

        events = pd.DataFrame({"type": ["Word"], "text": ["test"]})
        result = ns.run_pipeline(["/remote"], events)

        assert result.loc[0, "processed"] == True  # noqa: E712
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# run_remote_pipeline
# ---------------------------------------------------------------------------


def test_run_remote_pipeline_chains_multiple_servers() -> None:
    server1 = ChannelServer(transform=_add_processed_flag)
    server2 = ChannelServer(transform=_double_value)

    host1, port1 = server1.start()
    host2, port2 = server2.start()

    try:
        events = pd.DataFrame({"type": ["Word"], "value": [5]})
        result = run_remote_pipeline(events, [(host1, port1), (host2, port2)])

        assert result.loc[0, "processed"] == True  # noqa: E712
        assert result.loc[0, "value"] == 10
    finally:
        server1.stop()
        server2.stop()


def test_run_remote_pipeline_with_single_server() -> None:
    server = ChannelServer(transform=_add_processed_flag)
    host, port = server.start()

    try:
        events = pd.DataFrame({"type": ["Audio"]})
        result = run_remote_pipeline(events, [(host, port)])

        assert result.loc[0, "processed"] == True  # noqa: E712
    finally:
        server.stop()


def test_run_remote_pipeline_empty_servers_returns_input() -> None:
    events = pd.DataFrame({"type": ["Word"], "text": ["unchanged"]})
    result = run_remote_pipeline(events, [])

    pd.testing.assert_frame_equal(result, events)


# ---------------------------------------------------------------------------
# Concurrent connections
# ---------------------------------------------------------------------------


def test_server_handles_concurrent_clients() -> None:
    server = ChannelServer(transform=_add_processed_flag)
    host, port = server.start()

    results: list[pd.DataFrame] = []
    errors: list[Exception] = []

    def client_task(client_id: int) -> None:
        try:
            client = ChannelClient(host=host, port=port)
            client.connect()
            events = pd.DataFrame({"client_id": [client_id]})
            result = client.send(events)
            results.append(result)
            client.close()
        except Exception as e:
            errors.append(e)

    try:
        threads = [threading.Thread(target=client_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 5
        for r in results:
            assert r.loc[0, "processed"] == True  # noqa: E712
    finally:
        server.stop()
