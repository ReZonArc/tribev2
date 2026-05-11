import pandas as pd
import pytest

from tribev2.experimental import EventRewriteRule, EventRewriter, default_rewriter


def test_default_rewriter_populates_defaults_and_normalizes_words() -> None:
    events = pd.DataFrame(
        {
            "type": ["Word", "Audio"],
            "text": ["  hello   world  ", None],
            "start": [1.0, 2.0],
            "duration": [0.5, 0.2],
        }
    )

    out = default_rewriter().rewrite(events)

    assert out.loc[0, "timeline"] == "default"
    assert out.loc[1, "subject"] == "default"
    assert out.loc[0, "stop"] == 1.5
    assert out.loc[1, "stop"] == 2.2
    assert out.loc[0, "text"] == "hello world"
    assert pd.isna(out.loc[1, "text"])


def test_default_rewriter_does_not_mutate_input_by_default() -> None:
    events = pd.DataFrame(
        {"type": ["Word"], "text": ["  keep  spacing  "], "start": [0.0], "duration": [1.0]}
    )

    out = default_rewriter().rewrite(events)

    assert "timeline" not in events.columns
    assert events.loc[0, "text"] == "  keep  spacing  "
    assert out.loc[0, "text"] == "keep spacing"


def test_default_rewriter_returns_applied_rule_trace() -> None:
    events = pd.DataFrame({"type": ["Audio"], "start": [0.0], "duration": [1.0]})

    out, trace = default_rewriter().rewrite(events, return_trace=True)

    assert out.loc[0, "stop"] == 1.0
    assert trace == (
        "ensure_default_timeline_and_subject",
        "infer_stop_from_start_and_duration",
        "normalize_word_text",
    )


def test_contracts_can_be_enforced_or_disabled() -> None:
    events = pd.DataFrame({"type": ["Audio"], "start": [0.0], "duration": [1.0]})
    contracts = default_rewriter().contracts
    rewriter = EventRewriter(
        rules=(
            EventRewriteRule(
                name="break_stop",
                apply=lambda frame: frame.assign(
                    stop=pd.NA, timeline="default", subject="default"
                ),
            ),
        ),
        contracts=contracts,
    )

    with pytest.raises(ValueError, match="stop_matches_start_plus_duration"):
        rewriter.rewrite(events, enforce_contracts=True)

    out = rewriter.rewrite(events, enforce_contracts=False)
    assert pd.isna(out.loc[0, "stop"])
