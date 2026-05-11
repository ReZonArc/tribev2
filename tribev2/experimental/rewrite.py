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

    def rewrite(self, events: pd.DataFrame, copy_input: bool = True) -> pd.DataFrame:
        """Apply rewrite rules in order.

        When ``copy_input`` is True (default), the rewriter first copies ``events``
        and rules run against that copy.
        When False, the original dataframe is passed directly to rules and may be
        mutated in-place.
        """
        out = events.copy() if copy_input else events
        for rule in self.rules:
            out = rule.apply(out)
        return out


def _ensure_default_timeline_and_subject(events: pd.DataFrame) -> pd.DataFrame:
    """Rewrite in-place: ensure non-null timeline/subject fields."""
    for column in ("timeline", "subject"):
        if column not in events.columns:
            events[column] = "default"
        else:
            events[column] = events[column].fillna("default")
    return events


def _infer_stop_from_start_and_duration(events: pd.DataFrame) -> pd.DataFrame:
    """Rewrite in-place: populate stop from start+duration when missing."""
    if "start" in events.columns and "duration" in events.columns:
        has_stop = "stop" in events.columns
        if has_stop:
            missing_stop = events["stop"].isna()
            if missing_stop.any():
                events.loc[missing_stop, "stop"] = (
                    events.loc[missing_stop, "start"]
                    + events.loc[missing_stop, "duration"]
                )
        else:
            events["stop"] = events["start"] + events["duration"]
    return events


def _normalize_word_text(events: pd.DataFrame) -> pd.DataFrame:
    """Rewrite in-place: trim/normalize whitespace for Word event text."""
    if "type" not in events.columns or "text" not in events.columns:
        return events
    is_word = events["type"] == "Word"
    word_text = events.loc[is_word, "text"]
    if not pd.api.types.is_string_dtype(word_text):
        word_text = word_text.astype(str)
    normalized_text = word_text.str.strip().str.replace(r"\s+", " ", regex=True)
    events.loc[is_word, "text"] = normalized_text
    return events


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
