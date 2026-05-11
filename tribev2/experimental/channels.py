# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Limbo / Inferno-style distributed namespace for event pipeline services.

Provides:
- ``EventChannel``: typed, buffered channel for passing event DataFrames between
  pipeline stages (inspired by Limbo's ``chan`` type).
- ``ChannelService``: a named service that reads events from an input channel,
  applies a transform, and writes results to an output channel.
- ``ServiceNamespace``: a namespace where services are mounted at named paths
  and composed into pipelines (inspired by Plan 9 / Inferno bind/mount).
"""

import queue
import threading
import typing as tp
from dataclasses import dataclass, field

import pandas as pd


TransformFn = tp.Callable[[pd.DataFrame], pd.DataFrame]

# Sentinel used to signal that a channel has been closed.
_CLOSED: pd.DataFrame = pd.DataFrame()


class EventChannel:
    """A typed, buffered channel for passing event DataFrames between stages.

    Inspired by Limbo's ``chan`` type.  Producers call :meth:`send`; consumers
    call :meth:`recv`.  Call :meth:`close` when no more events will be sent.
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: queue.Queue[pd.DataFrame] = queue.Queue(maxsize=maxsize)
        self._closed = False

    def send(self, events: pd.DataFrame) -> None:
        """Send an event DataFrame through the channel.

        Raises ``RuntimeError`` if the channel is already closed.
        """
        if self._closed:
            raise RuntimeError("send on a closed EventChannel")
        self._queue.put(events)

    def recv(self) -> pd.DataFrame | None:
        """Receive an event DataFrame.

        Returns ``None`` when the channel has been closed and all queued items
        have been consumed.
        """
        item = self._queue.get()
        if item is _CLOSED:
            return None
        return item

    def close(self) -> None:
        """Signal that no more events will be sent on this channel."""
        self._closed = True
        self._queue.put(_CLOSED)


@dataclass(frozen=True)
class ChannelService:
    """A named pipeline service that transforms events from an input to an output channel.

    Inspired by Limbo processes: the service reads a DataFrame from *input_chan*,
    applies *transform*, and writes the result to *output_chan*.  When *input_chan*
    is closed, the service closes *output_chan* and exits.

    Call :meth:`start` to run the service in a background daemon thread.
    """

    name: str
    transform: TransformFn

    def start(
        self,
        input_chan: EventChannel,
        output_chan: EventChannel,
    ) -> threading.Thread:
        """Start the service in a background daemon thread and return the thread."""
        thread = threading.Thread(
            target=self._run,
            args=(input_chan, output_chan),
            name=self.name,
            daemon=True,
        )
        thread.start()
        return thread

    def _run(
        self,
        input_chan: EventChannel,
        output_chan: EventChannel,
    ) -> None:
        while True:
            events = input_chan.recv()
            if events is None:
                output_chan.close()
                return
            output_chan.send(self.transform(events))


@dataclass
class ServiceNamespace:
    """A namespace where pipeline services are mounted at named paths.

    Inspired by Plan 9 / Inferno's namespace model: services are mounted at
    path-like names and can be composed into sequential pipelines.

    Example::

        ns = ServiceNamespace()
        ns.mount("/normalize", ChannelService("normalize", my_normalize_fn))
        ns.mount("/extract",   ChannelService("extract",   my_extract_fn))

        # Sequential execution in the calling thread:
        result = ns.run_pipeline(["/normalize", "/extract"], events)

        # Channel-based execution (each stage in its own thread):
        result = ns.run_pipeline(["/normalize", "/extract"], events, threaded=True)
    """

    _mounts: dict[str, ChannelService] = field(default_factory=dict)

    def mount(self, path: str, service: ChannelService) -> None:
        """Mount *service* at *path* in the namespace."""
        self._mounts[_normalize_path(path)] = service

    def unmount(self, path: str) -> None:
        """Unmount the service at *path*.  No-op if nothing is mounted there."""
        self._mounts.pop(_normalize_path(path), None)

    def get(self, path: str) -> ChannelService | None:
        """Return the service mounted at *path*, or ``None``."""
        return self._mounts.get(_normalize_path(path))

    def list_mounts(self) -> tuple[str, ...]:
        """Return all mounted paths in sorted order."""
        return tuple(sorted(self._mounts))

    def compose(self, *paths: str) -> TransformFn:
        """Return a sequential pipeline callable from the services at *paths*.

        The returned function applies each service's transform in order.
        Raises ``KeyError`` if any path is not mounted.
        """
        services = _resolve_services(self, paths)

        def pipeline(events: pd.DataFrame) -> pd.DataFrame:
            for service in services:
                events = service.transform(events)
            return events

        return pipeline

    def run_pipeline(
        self,
        paths: tp.Sequence[str],
        events: pd.DataFrame,
        *,
        threaded: bool = False,
    ) -> pd.DataFrame:
        """Run *events* through the services mounted at *paths*.

        Parameters
        ----------
        paths:
            Ordered sequence of namespace paths identifying services to apply.
        events:
            Input event DataFrame.
        threaded:
            When ``True`` each service runs in its own daemon thread connected
            by ``EventChannel`` objects (Limbo-style channel passing).
            When ``False`` (default) the pipeline runs sequentially in the
            calling thread.
        """
        if not threaded:
            return self.compose(*paths)(events)
        return _run_threaded(self, paths, events)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_path(path: str) -> str:
    """Return a canonical leading-slash path string."""
    return "/" + path.strip("/")


def _resolve_services(
    ns: ServiceNamespace,
    paths: tp.Sequence[str],
) -> list[ChannelService]:
    """Look up and return services for each path; raise ``KeyError`` if missing."""
    services: list[ChannelService] = []
    for path in paths:
        service = ns.get(path)
        if service is None:
            raise KeyError(f"No service mounted at {path!r}")
        services.append(service)
    return services


def _run_threaded(
    ns: ServiceNamespace,
    paths: tp.Sequence[str],
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Run a pipeline through channel-connected threads and return the result."""
    services = _resolve_services(ns, paths)
    n = len(services)

    # Create n+1 channels: input → svc0 → svc1 → … → svcN-1 → output
    channels = [EventChannel() for _ in range(n + 1)]

    # Start each service in its own thread.
    threads: list[threading.Thread] = []
    for service, input_chan, output_chan in zip(services, channels[:-1], channels[1:]):
        threads.append(service.start(input_chan, output_chan))

    # Feed the input DataFrame into the first channel, then close it.
    channels[0].send(events)
    channels[0].close()

    # Collect the single result DataFrame from the last channel.
    result = channels[-1].recv()

    for thread in threads:
        thread.join()

    return result if result is not None else pd.DataFrame()
