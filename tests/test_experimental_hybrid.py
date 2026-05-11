import pandas as pd

from tribev2.experimental import HybridRuntime, default_rewriter, render_maude_module


def test_render_maude_module_emits_rules_and_contract_comments() -> None:
    text = render_maude_module(default_rewriter(), module_name="TEST-MOD")

    assert "fmod TEST-MOD is" in text
    assert "rl [ensure_default_timeline_and_subject] : frame => frame ." in text
    assert "rl [infer_stop_from_start_and_duration] : frame => frame ." in text
    assert "rl [normalize_word_text] : frame => frame ." in text
    assert "--- contract: default_timeline_and_subject" in text


def test_hybrid_runtime_sequential_matches_default_rewriter() -> None:
    events = pd.DataFrame(
        {
            "type": ["Word", "Audio"],
            "text": ["  hello   world  ", None],
            "start": [1.0, 2.0],
            "duration": [0.5, 0.2],
        }
    )
    rewriter = default_rewriter()
    expected = rewriter.rewrite(events)

    runtime = HybridRuntime(rewriter=rewriter)
    out, trace = runtime.run_with_trace(events)

    pd.testing.assert_frame_equal(out, expected)
    assert trace == (
        "ensure_default_timeline_and_subject",
        "infer_stop_from_start_and_duration",
        "normalize_word_text",
    )


def test_hybrid_runtime_threaded_and_sequential_match() -> None:
    events = pd.DataFrame(
        {
            "type": ["Word"],
            "text": ["  keep  spacing  "],
            "start": [0.0],
            "duration": [1.0],
        }
    )
    runtime = HybridRuntime(rewriter=default_rewriter())

    seq = runtime.run(events, threaded=False)
    thr = runtime.run(events, threaded=True)

    pd.testing.assert_frame_equal(seq, thr)


def test_hybrid_runtime_slash_prefix_maps_to_root_paths() -> None:
    runtime = HybridRuntime(rewriter=default_rewriter(), rewrite_prefix="///")
    assert runtime.rewrite_paths()[0].startswith("/00-")
