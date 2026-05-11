# Initial Steps Implemented (Maude/9P/Limbo exploration track)

This document records the first concrete implementation steps added in-repo.

## ✅ Step 1 implemented: explicit rewriting scaffold for event transformations

Added:
- `/home/runner/work/tribev2/tribev2/tribev2/experimental/rewrite.py`
- `/home/runner/work/tribev2/tribev2/tribev2/experimental/__init__.py`

What this provides:
- `EventRewriteRule`: named, composable event rewrite rule
- `EventRewriter`: deterministic pipeline runner over pandas DataFrames
- built-in starter rules:
  - `ensure_default_timeline_and_subject`
  - `infer_stop_from_start_and_duration`
  - `normalize_word_text`

Why this is the right first step:
- It directly mirrors the event-pipeline structure already used by TRIBE v2.
- It is zero-disruption to existing training/inference APIs.
- It creates a clean handoff point to future Maude formal rules or alternate runtimes.

## Suggested next steps (not yet implemented)

1. Add a translator from `EventRewriteRule` sets to Maude module text.
2. Add a rule-execution trace serializer for reproducibility/debugging.
3. Add a file-backed adapter layer to expose rewrite pipeline I/O in a 9P-friendly namespace shape.
4. Add integration hook in `demo_utils.get_audio_and_text_events` as an optional post-normalization stage.
