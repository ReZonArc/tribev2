# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Remote-capable channels for distributed event pipeline execution.

Provides socket-based channels that allow pipeline services to run on separate
nodes, extending the Limbo-style channel model to a distributed setting.

Key components:

- ``RemoteEventChannel``: A channel that can send/receive events over a socket.
- ``ChannelServer``: Listens for remote channel connections and dispatches to a service.
- ``ChannelClient``: Connects to a remote channel server and sends/receives events.
"""

import io
import json
import socket
import struct
import threading
import typing as tp
from dataclasses import dataclass

import pandas as pd

from .channels import TransformFn


# Protocol constants
_HEADER_SIZE = 8  # 8 bytes for payload length (uint64)
_MSG_DATA = b"\x01"
_MSG_CLOSE = b"\x02"


def _encode_frame(events: pd.DataFrame) -> bytes:
    """Encode a DataFrame to bytes for transmission."""
    buffer = io.BytesIO()
    events.to_json(buffer, orient="records", lines=True)
    return buffer.getvalue()


def _decode_frame(data: bytes) -> pd.DataFrame:
    """Decode bytes back to a DataFrame."""
    if not data:
        return pd.DataFrame()
    return pd.read_json(io.BytesIO(data), orient="records", lines=True)


def _send_message(sock: socket.socket, msg_type: bytes, payload: bytes) -> None:
    """Send a typed message over the socket with length prefix."""
    header = struct.pack(">Q", len(payload))
    sock.sendall(msg_type + header + payload)


def _recv_message(sock: socket.socket) -> tuple[bytes, bytes]:
    """Receive a typed message from the socket.

    Returns
    -------
    tuple[bytes, bytes]
        (message_type, payload) where message_type is 1 byte.
    """
    msg_type = sock.recv(1)
    if not msg_type:
        return b"", b""
    header = sock.recv(_HEADER_SIZE)
    if len(header) < _HEADER_SIZE:
        return msg_type, b""
    (length,) = struct.unpack(">Q", header)
    if length == 0:
        return msg_type, b""
    chunks: list[bytes] = []
    received = 0
    while received < length:
        chunk = sock.recv(min(length - received, 65536))
        if not chunk:
            break
        chunks.append(chunk)
        received += len(chunk)
    return msg_type, b"".join(chunks)


@dataclass
class ChannelServer:
    """A server that accepts remote channel connections and applies a transform.

    The server listens on a specified host:port and applies the given transform
    function to incoming event DataFrames, returning the results over the socket.

    Example::

        def my_transform(events: pd.DataFrame) -> pd.DataFrame:
            return events.assign(processed=True)

        server = ChannelServer(transform=my_transform, host="0.0.0.0", port=9999)
        server.start()  # Runs in background thread
        # ... later ...
        server.stop()

    Parameters
    ----------
    transform:
        Function that transforms input events to output events.
    host:
        Host address to bind to.
    port:
        Port number to listen on.
    """

    transform: TransformFn
    host: str = "127.0.0.1"
    port: int = 0  # 0 means OS assigns a free port

    _server_socket: socket.socket | None = None
    _thread: threading.Thread | None = None
    _shutdown: bool = False

    def __post_init__(self) -> None:
        # Convert defaults to instance attributes for mutability
        object.__setattr__(self, "_server_socket", None)
        object.__setattr__(self, "_thread", None)
        object.__setattr__(self, "_shutdown", False)

    @property
    def bound_address(self) -> tuple[str, int] | None:
        """Return the bound (host, port) tuple, or None if not started."""
        if self._server_socket is None:
            return None
        return self._server_socket.getsockname()

    def start(self) -> tuple[str, int]:
        """Start the server in a background daemon thread.

        Returns
        -------
        tuple[str, int]
            The (host, port) the server is listening on.
        """
        self._shutdown = False
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)  # Allow periodic shutdown checks

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self.bound_address  # type: ignore[return-value]

    def stop(self) -> None:
        """Stop the server and wait for the thread to exit."""
        self._shutdown = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if self._server_socket is not None:
            self._server_socket.close()
            self._server_socket = None

    def _serve(self) -> None:
        """Internal server loop."""
        while not self._shutdown:
            try:
                conn, _ = self._server_socket.accept()  # type: ignore[union-attr]
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_connection, args=(conn,), daemon=True
            ).start()

    def _handle_connection(self, conn: socket.socket) -> None:
        """Handle a single client connection."""
        try:
            while True:
                msg_type, payload = _recv_message(conn)
                if msg_type == _MSG_CLOSE or not msg_type:
                    break
                if msg_type == _MSG_DATA:
                    input_events = _decode_frame(payload)
                    output_events = self.transform(input_events)
                    _send_message(conn, _MSG_DATA, _encode_frame(output_events))
        except Exception:
            pass
        finally:
            conn.close()


@dataclass
class ChannelClient:
    """A client that connects to a remote channel server.

    Example::

        client = ChannelClient(host="127.0.0.1", port=9999)
        client.connect()
        result = client.send(events)
        client.close()

    Parameters
    ----------
    host:
        Host address to connect to.
    port:
        Port number to connect to.
    """

    host: str
    port: int

    _socket: socket.socket | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "_socket", None)

    def connect(self, timeout: float = 30.0) -> None:
        """Connect to the remote server.

        Parameters
        ----------
        timeout:
            Connection timeout in seconds.
        """
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(timeout)
        self._socket.connect((self.host, self.port))

    def send(self, events: pd.DataFrame) -> pd.DataFrame:
        """Send events to the server and receive the transformed result.

        Parameters
        ----------
        events:
            Input events DataFrame.

        Returns
        -------
        pd.DataFrame
            Transformed events DataFrame from the server.

        Raises
        ------
        RuntimeError
            If not connected.
        """
        if self._socket is None:
            raise RuntimeError("ChannelClient is not connected")
        _send_message(self._socket, _MSG_DATA, _encode_frame(events))
        msg_type, payload = _recv_message(self._socket)
        if msg_type != _MSG_DATA:
            return pd.DataFrame()
        return _decode_frame(payload)

    def close(self) -> None:
        """Close the connection to the server."""
        if self._socket is not None:
            try:
                _send_message(self._socket, _MSG_CLOSE, b"")
            except Exception:
                pass
            self._socket.close()
            self._socket = None


@dataclass(frozen=True)
class RemoteChannelService:
    """A channel service that delegates to a remote server.

    This allows mounting a remote transform as if it were a local service
    in the ``ServiceNamespace``.

    Parameters
    ----------
    name:
        Service name.
    host:
        Remote server host.
    port:
        Remote server port.
    """

    name: str
    host: str
    port: int

    @property
    def transform(self) -> TransformFn:
        """Return a transform function that delegates to the remote server."""
        host, port = self.host, self.port

        def remote_transform(events: pd.DataFrame) -> pd.DataFrame:
            client = ChannelClient(host=host, port=port)
            client.connect()
            try:
                return client.send(events)
            finally:
                client.close()

        return remote_transform


def run_remote_pipeline(
    events: pd.DataFrame,
    servers: tp.Sequence[tuple[str, int]],
) -> pd.DataFrame:
    """Run events through a sequence of remote servers.

    Parameters
    ----------
    events:
        Input events DataFrame.
    servers:
        Sequence of (host, port) tuples for remote servers to call in order.

    Returns
    -------
    pd.DataFrame
        Final transformed events after passing through all servers.
    """
    result = events
    for host, port in servers:
        client = ChannelClient(host=host, port=port)
        client.connect()
        try:
            result = client.send(result)
        finally:
            client.close()
    return result
