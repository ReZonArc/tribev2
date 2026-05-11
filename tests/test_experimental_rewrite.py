import pandas as pd

from tribev2.experimental import default_rewriter


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
