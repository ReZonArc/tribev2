# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Rule-execution trace serialization for reproducibility and debugging.

Provides utilities to persist and load the output of ``HybridRuntime.run_with_trace``
or ``EventRewriter.rewrite_with_trace`` as structured artifacts.
"""

import json
import typing as tp
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class RewriteTraceRecord:
    """A single recorded trace from a rewrite pipeline execution.

    Attributes
    ----------
    applied_rules:
        Tuple of rule names applied during rewriting, in execution order.
    input_events_digest:
        A short digest of the input events frame (row count + column hash).
    output_events_digest:
        A short digest of the output events frame.
    timestamp:
        ISO 8601 timestamp when the trace was created.
    metadata:
        Optional user-provided metadata dict.
    """

    applied_rules: tuple[str, ...]
    input_events_digest: str
    output_events_digest: str
    timestamp: str
    metadata: dict[str, tp.Any] | None = None


def _events_digest(events: pd.DataFrame) -> str:
    """Compute a compact digest string for an events DataFrame."""
    row_count = len(events)
    cols = tuple(sorted(events.columns.tolist()))
    cols_hash = hash(cols) & 0xFFFFFFFF
    return f"rows={row_count};cols_hash={cols_hash:08x}"


def create_trace_record(
    input_events: pd.DataFrame,
    output_events: pd.DataFrame,
    applied_rules: tuple[str, ...],
    metadata: dict[str, tp.Any] | None = None,
) -> RewriteTraceRecord:
    """Create a trace record from rewrite execution inputs and outputs.

    Parameters
    ----------
    input_events:
        The events DataFrame before rewriting.
    output_events:
        The events DataFrame after rewriting.
    applied_rules:
        Tuple of rule names that were applied.
    metadata:
        Optional user-provided metadata to include in the trace.

    Returns
    -------
    RewriteTraceRecord
        A frozen trace record suitable for serialization.
    """
    return RewriteTraceRecord(
        applied_rules=applied_rules,
        input_events_digest=_events_digest(input_events),
        output_events_digest=_events_digest(output_events),
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata=metadata,
    )


def serialize_trace(record: RewriteTraceRecord) -> str:
    """Serialize a trace record to JSON string."""
    data = asdict(record)
    # Convert tuple to list for JSON compatibility
    data["applied_rules"] = list(data["applied_rules"])
    return json.dumps(data, indent=2, ensure_ascii=False)


def deserialize_trace(text: str) -> RewriteTraceRecord:
    """Deserialize a trace record from JSON string."""
    data = json.loads(text)
    # Convert list back to tuple
    data["applied_rules"] = tuple(data["applied_rules"])
    return RewriteTraceRecord(**data)


def save_trace(record: RewriteTraceRecord, path: str | Path) -> Path:
    """Save a trace record to a JSON file.

    Parameters
    ----------
    record:
        The trace record to save.
    path:
        Path to the output file.

    Returns
    -------
    Path
        The path where the trace was written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_trace(record), encoding="utf-8")
    return path


def load_trace(path: str | Path) -> RewriteTraceRecord:
    """Load a trace record from a JSON file.

    Parameters
    ----------
    path:
        Path to the input file.

    Returns
    -------
    RewriteTraceRecord
        The deserialized trace record.
    """
    return deserialize_trace(Path(path).read_text(encoding="utf-8"))


@dataclass
class TraceStore:
    """A simple trace store backed by a directory.

    All traces are stored as JSON files named by their creation timestamp.

    Parameters
    ----------
    root:
        Root directory for trace files.
    """

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        input_events: pd.DataFrame,
        output_events: pd.DataFrame,
        applied_rules: tuple[str, ...],
        metadata: dict[str, tp.Any] | None = None,
        name: str | None = None,
    ) -> Path:
        """Create and save a trace record to the store.

        Parameters
        ----------
        input_events:
            The events DataFrame before rewriting.
        output_events:
            The events DataFrame after rewriting.
        applied_rules:
            Tuple of rule names that were applied.
        metadata:
            Optional user-provided metadata.
        name:
            Optional filename (without extension). If not provided, uses timestamp.

        Returns
        -------
        Path
            The path where the trace was saved.
        """
        record = create_trace_record(
            input_events=input_events,
            output_events=output_events,
            applied_rules=applied_rules,
            metadata=metadata,
        )
        if name is None:
            # Use timestamp-based name (replace colons for filesystem safety)
            name = record.timestamp.replace(":", "-").replace("+", "_")
        return save_trace(record, self.root / f"{name}.json")

    def list_traces(self) -> tuple[Path, ...]:
        """Return all trace file paths in the store, sorted by name."""
        return tuple(sorted(self.root.glob("*.json")))

    def load_all(self) -> tuple[RewriteTraceRecord, ...]:
        """Load all trace records from the store."""
        return tuple(load_trace(p) for p in self.list_traces())
