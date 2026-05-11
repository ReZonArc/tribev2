# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Hybrid DSL bridge: Maude-style rewrite semantics + Limbo-style execution."""

from dataclasses import dataclass, field

import pandas as pd

from .channels import ChannelService, ServiceNamespace
from .rewrite import EventRewriter

DEFAULT_REWRITE_PREFIX = "/rewrite"


def _dsl_identifier(name: str) -> str:
    identifier = "".join(ch if ch.isalnum() else "_" for ch in name.strip())
    if not identifier:
        identifier = "unnamed_rule"
    if identifier[0].isdigit():
        identifier = f"rule_{identifier}"
    return identifier.lower()


def render_maude_module(
    rewriter: EventRewriter,
    module_name: str = "TRIBEV2-EVENT-REWRITE",
) -> str:
    """Render a conservative Maude-style module text from rewrite declarations."""
    lines = [
        f"fmod {module_name} is",
        "  --- Auto-generated from tribev2.experimental.EventRewriter",
        "  sort EventFrame .",
        "  op frame : -> EventFrame [ctor] .",
    ]
    if not rewriter.rules:
        lines.append("  --- no rewrite rules declared")
    for rule in rewriter.rules:
        lines.append(f"  rl [{_dsl_identifier(rule.name)}] : frame => frame .")
    for contract in rewriter.contracts:
        lines.append(f"  --- contract: {contract.name}")
    lines.append("endfm")
    return "\n".join(lines)


@dataclass
class HybridRuntime:
    """Bridge rewrite semantics and channel-based runtime execution."""

    rewriter: EventRewriter
    namespace: ServiceNamespace = field(default_factory=ServiceNamespace)
    rewrite_prefix: str = DEFAULT_REWRITE_PREFIX

    def __post_init__(self) -> None:
        self._mount_rule_services()

    def _mount_rule_services(self) -> None:
        for index, rule in enumerate(self.rewriter.rules):
            self.namespace.mount(
                self._path_for_rule(index, rule.name),
                ChannelService(name=f"rewrite:{rule.name}", transform=rule.apply),
            )

    def _path_for_rule(self, index: int, rule_name: str) -> str:
        prefix = "/" + self.rewrite_prefix.strip("/")
        return f"{prefix}/{index:02d}-{_dsl_identifier(rule_name)}"

    def rewrite_paths(self) -> tuple[str, ...]:
        return tuple(
            self._path_for_rule(index, rule.name)
            for index, rule in enumerate(self.rewriter.rules)
        )

    def maude_module(self, module_name: str = "TRIBEV2-EVENT-REWRITE") -> str:
        return render_maude_module(self.rewriter, module_name=module_name)

    def run(
        self,
        events: pd.DataFrame,
        *,
        threaded: bool = False,
        copy_input: bool = True,
        enforce_contracts: bool = True,
    ) -> pd.DataFrame:
        out = events.copy() if copy_input else events
        paths = self.rewrite_paths()
        if paths:
            out = self.namespace.run_pipeline(paths, out, threaded=threaded)
        if enforce_contracts:
            for contract in self.rewriter.contracts:
                contract.validate(out)
        return out

    def run_with_trace(
        self,
        events: pd.DataFrame,
        *,
        threaded: bool = False,
        copy_input: bool = True,
        enforce_contracts: bool = True,
    ) -> tuple[pd.DataFrame, tuple[str, ...]]:
        out = self.run(
            events,
            threaded=threaded,
            copy_input=copy_input,
            enforce_contracts=enforce_contracts,
        )
        trace = tuple(rule.name for rule in self.rewriter.rules)
        return out, trace
