# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import typing as tp
from dataclasses import dataclass

import pandas as pd


RewriteFn = tp.Callable[[pd.DataFrame], pd.DataFrame]


@dataclass(frozen=True)
class EventRewriteRule:
    name: str
    apply: RewriteFn


@dataclass(frozen=True)
class EventRewriter:
    rules: tuple[EventRewriteRule, ...]

    def rewrite(self, events: pd.DataFrame) -> pd.DataFrame:
        out = events.copy()
        for rule in self.rules:
            out = rule.apply(out)
        return out


def _ensure_default_timeline_and_subject(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    if "timeline" not in out.columns:
        out["timeline"] = "default"
    else:
        out["timeline"] = out["timeline"].fillna("default")
    if "subject" not in out.columns:
        out["subject"] = "default"
    else:
        out["subject"] = out["subject"].fillna("default")
    return out


def _infer_stop_from_start_and_duration(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    if "start" in out.columns and "duration" in out.columns:
        has_stop = "stop" in out.columns
        stop = out["start"] + out["duration"]
        if has_stop:
            out["stop"] = out["stop"].fillna(stop)
        else:
            out["stop"] = stop
    return out


def _normalize_word_text(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    if "type" not in out.columns or "text" not in out.columns:
        return out
    is_word = out["type"] == "Word"
    out.loc[is_word, "text"] = (
        out.loc[is_word, "text"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    )
    return out


def default_rewriter() -> EventRewriter:
    return EventRewriter(
        rules=(
            EventRewriteRule(
                name="ensure_default_timeline_and_subject",
                apply=_ensure_default_timeline_and_subject,
            ),
            EventRewriteRule(
                name="infer_stop_from_start_and_duration",
                apply=_infer_stop_from_start_and_duration,
            ),
            EventRewriteRule(name="normalize_word_text", apply=_normalize_word_text),
        )
    )
