# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import typing as tp
from dataclasses import dataclass

import pandas as pd


RewriteFn = tp.Callable[[pd.DataFrame], pd.DataFrame]
ContractFn = tp.Callable[[pd.DataFrame], bool]
# Event times are represented in seconds in TRIBE event dataframes.
FLOAT_COMPARISON_TOLERANCE = 1e-9


@dataclass(frozen=True)
class EventRewriteRule:
    name: str
    apply: RewriteFn


@dataclass(frozen=True)
class EventNormalizationContract:
    name: str
    check: ContractFn
    violation_message: str

    def validate(self, events: pd.DataFrame) -> None:
        if not self.check(events):
            raise ValueError(f"{self.name}: {self.violation_message}")


@dataclass(frozen=True)
class EventRewriter:
    rules: tuple[EventRewriteRule, ...]
    contracts: tuple[EventNormalizationContract, ...] = ()

    def rewrite(
        self,
        events: pd.DataFrame,
        copy_input: bool = True,
        enforce_contracts: bool = True,
        return_trace: bool = False,
    ) -> pd.DataFrame | tuple[pd.DataFrame, tuple[str, ...]]:
        """Apply rewrite rules in order.

        When ``copy_input`` is True (default), the rewriter first copies ``events``
        and rules run against that copy.
        When False, the original dataframe is passed directly to rules and may be
        mutated in-place.
        When ``enforce_contracts`` is True (default), all contracts are validated
        after rules are applied and a ``ValueError`` is raised on violation.
        When ``return_trace`` is True, a tuple with the applied rule names is
        returned alongside the rewritten dataframe.
        """
        out = events.copy() if copy_input else events
        applied_rules: list[str] = []
        for rule in self.rules:
            out = rule.apply(out)
            applied_rules.append(rule.name)
        if enforce_contracts:
            for contract in self.contracts:
                contract.validate(out)
        if return_trace:
            return out, tuple(applied_rules)
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
    if not is_word.any():
        return events

    word_text = events.loc[is_word, "text"]
    non_missing = word_text.notna()
    if not non_missing.any():
        return events

    normalized_text = (
        word_text.loc[non_missing]
        .astype("string")
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )
    events.loc[normalized_text.index, "text"] = normalized_text
    return events


def _contract_has_default_timeline_and_subject(events: pd.DataFrame) -> bool:
    for column in ("timeline", "subject"):
        if column not in events.columns:
            return False
        if events[column].isna().any():
            return False
    return True


def _contract_stop_matches_start_plus_duration(events: pd.DataFrame) -> bool:
    required = {"start", "duration", "stop"}
    if not required.issubset(events.columns):
        return True
    has_start_duration = events["start"].notna() & events["duration"].notna()
    if not has_start_duration.any():
        return True
    if events.loc[has_start_duration, "stop"].isna().any():
        return False
    comparable = events.loc[has_start_duration, ["start", "duration", "stop"]]
    expected = comparable["start"] + comparable["duration"]
    return ((comparable["stop"] - expected).abs() <= FLOAT_COMPARISON_TOLERANCE).all()


def _contract_word_text_is_normalized(events: pd.DataFrame) -> bool:
    if "type" not in events.columns or "text" not in events.columns:
        return True
    word_text = events.loc[events["type"] == "Word", "text"].dropna()
    if word_text.empty:
        return True
    word_text_string = word_text.astype("string")
    normalized = word_text_string.str.strip().str.replace(r"\s+", " ", regex=True)
    return normalized.equals(word_text_string)


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
        ),
        contracts=(
            EventNormalizationContract(
                name="default_timeline_and_subject",
                check=_contract_has_default_timeline_and_subject,
                violation_message="timeline/subject must exist and be non-null",
            ),
            EventNormalizationContract(
                name="stop_matches_start_plus_duration",
                check=_contract_stop_matches_start_plus_duration,
                violation_message="stop must equal start + duration where all are set",
            ),
            EventNormalizationContract(
                name="word_text_is_normalized",
                check=_contract_word_text_is_normalized,
                violation_message=(
                    "Word text must be trimmed and contain single-space separators"
                ),
            ),
        ),
    )
