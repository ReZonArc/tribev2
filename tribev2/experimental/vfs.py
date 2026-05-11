# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
import typing as tp
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


def _normalize_virtual_path(path: str) -> Path:
    normalized = Path(path.strip("/"))
    if any(part == ".." for part in normalized.parts):
        raise ValueError(f"Path traversal is not allowed: {path!r}")
    return normalized


@dataclass(frozen=True)
class EventNamespaceFS:
    """File-backed namespace for model I/O and cached features.

    Namespace layout:
    - /inputs
    - /events
    - /outputs
    - /cache/features
    """

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))
        self.ensure_layout()

    def ensure_layout(self) -> None:
        for relative in ("inputs", "events", "outputs", "cache/features"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)

    def to_host_path(self, virtual_path: str) -> Path:
        relative = _normalize_virtual_path(virtual_path)
        return self.root / relative

    def list_virtual_paths(self) -> tuple[str, ...]:
        base_dirs = [self.root / "inputs", self.root / "events", self.root / "outputs"]
        base_dirs.append(self.root / "cache" / "features")
        paths: set[str] = set()
        for directory in base_dirs:
            if not directory.exists():
                continue
            for host_path in directory.rglob("*"):
                if host_path.is_file():
                    paths.add("/" + host_path.relative_to(self.root).as_posix())
        return tuple(sorted(paths))

    def read_bytes(self, virtual_path: str) -> bytes:
        return self.to_host_path(virtual_path).read_bytes()

    def read_text(self, virtual_path: str, encoding: str = "utf-8") -> str:
        return self.to_host_path(virtual_path).read_text(encoding=encoding)

    def write_input_text(self, name: str, text: str, encoding: str = "utf-8") -> str:
        host_path = self.root / "inputs" / _normalize_virtual_path(name)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_text(text, encoding=encoding)
        return "/" + host_path.relative_to(self.root).as_posix()

    def write_events(self, events: pd.DataFrame, name: str = "events.jsonl") -> str:
        host_path = self.root / "events" / _normalize_virtual_path(name)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_text(events.to_json(orient="records", lines=True), encoding="utf-8")
        return "/" + host_path.relative_to(self.root).as_posix()

    def write_output_json(self, name: str, payload: tp.Any) -> str:
        host_path = self.root / "outputs" / _normalize_virtual_path(name)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return "/" + host_path.relative_to(self.root).as_posix()

    def write_cached_feature_bytes(self, name: str, data: bytes) -> str:
        host_path = self.root / "cache" / "features" / _normalize_virtual_path(name)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_bytes(data)
        return "/" + host_path.relative_to(self.root).as_posix()
