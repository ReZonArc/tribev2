# Initial Steps Implemented (Maude/9P/Limbo exploration track)

This document records the first concrete implementation steps added in-repo.

## ✅ Step 1 implemented: explicit rewriting scaffold for event transformations

Added:
- `tribev2/experimental/rewrite.py`
- `tribev2/experimental/__init__.py`

What this provides:
- `EventRewriteRule`: named, composable event rewrite rule
- `EventRewriter`: deterministic pipeline runner over pandas DataFrames
- `EventNormalizationContract`: explicit post-rewrite normalization contract checks
- built-in starter rules:
  - `ensure_default_timeline_and_subject`
  - `infer_stop_from_start_and_duration`
  - `normalize_word_text`
- built-in starter contracts:
  - `default_timeline_and_subject`
  - `stop_matches_start_plus_duration`
  - `word_text_is_normalized`
- optional rule-execution trace output for reproducibility/auditability

Why this is the right first step:
- It directly mirrors the event-pipeline structure already used by TRIBE v2.
- It is zero-disruption to existing training/inference APIs.
- It creates a clean handoff point to future Maude formal rules or alternate runtimes.

## ✅ Step 2 implemented: file-backed 9P-friendly namespace adapter

Added:
- `tribev2/experimental/vfs.py`

What this provides:
- `EventNamespaceFS`: lightweight virtual namespace shape over a local folder
- canonical paths for composable tooling:
  - `/inputs/*`
  - `/events/*`
  - `/outputs/*`
  - `/cache/features/*`
- path-safe read/write helpers for inputs, event frames, outputs, and cached features

## ✅ Step 3 implemented: Limbo / Inferno-style distributed namespace

Added:
- `tribev2/experimental/channels.py`

What this provides:
- `EventChannel`: a typed, buffered channel for passing event DataFrames between
  pipeline stages, inspired by Limbo's `chan` type.  Producers call `send()`;
  consumers call `recv()`; `close()` signals end-of-stream.
- `ChannelService`: a named pipeline service that reads from an input channel,
  applies a transform function, and writes results to an output channel.  Each
  service runs in its own daemon thread when started with `start()`.
- `ServiceNamespace`: a namespace where services are mounted at named paths
  (inspired by Plan 9 / Inferno `bind`/`mount`).  Supports:
  - `mount(path, service)` / `unmount(path)` / `list_mounts()`
  - `compose(*paths)` → returns a sequential pipeline callable
  - `run_pipeline(paths, events)` → sequential execution in the calling thread
  - `run_pipeline(paths, events, threaded=True)` → channel-based execution with
    one daemon thread per service (full Limbo-style channel passing)

Why this is the right next step:
- It directly extends the rewrite/vfs scaffold to distributed execution.
- Each pipeline stage (event normalization, feature extraction, etc.) can be
  mounted as an independent service and composed by namespace path.
- `threaded=True` provides true channel-based stage separation with no shared
  mutable state between services — matching the Inferno/Limbo concurrency model.
- Fully zero-disruption: existing training/inference APIs are unchanged.

## ✅ Step 4 implemented: hybrid DSL bridge (Maude semantics + Limbo execution)

Added:
- `tribev2/experimental/hybrid.py`

What this provides:
- `render_maude_module`: emits conservative Maude-style module text from
  `EventRewriter` declarations (rules + contracts).
- `HybridRuntime`: mounts each rewrite rule into a `ServiceNamespace` and runs
  the rewrite pipeline either sequentially or with channel-based threaded
  execution.
- `run_with_trace`: returns both transformed events and an explicit rule trace,
  preserving semantic transparency while using the operational runtime model.

Why this is the right next step:
- It combines formalized rewrite declarations with practical channel-based
  execution in one minimal bridge API.
- It keeps behavior aligned with existing rewrite contracts while enabling
  Limbo-style runtime composition.
- Existing training/inference APIs remain unchanged.

## ✅ Step 5 implemented: rule-execution trace serializer

Added:
- `tribev2/experimental/trace.py`

What this provides:
- `RewriteTraceRecord`: a frozen dataclass capturing applied rules, event digests,
  timestamp, and optional metadata.
- `create_trace_record`: creates a trace record from rewrite execution inputs/outputs.
- `serialize_trace` / `deserialize_trace`: JSON serialization for trace records.
- `save_trace` / `load_trace`: file I/O helpers for trace persistence.
- `TraceStore`: a simple directory-backed trace store for managing multiple traces.

Why this is the right step:
- Enables reproducibility and debugging by persisting `run_with_trace` output.
- Provides audit trails for event pipeline transformations.
- Supports compliance and quality assurance workflows.

## ✅ Step 6 implemented: integration hook in demo_utils

Updated:
- `tribev2/demo_utils.py`

What this provides:
- `get_audio_and_text_events` now accepts an optional `normalize_events=True`
  parameter that applies the experimental event normalization rewriter as a
  final post-processing step.

Why this is the right step:
- Provides a zero-friction way to enable event normalization in the main
  inference pipeline.
- Maintains backward compatibility (normalization is off by default).
- Demonstrates practical integration of the experimental rewrite scaffold.

## ✅ Step 7 implemented: remote-capable channels

Added:
- `tribev2/experimental/remote.py`

What this provides:
- `ChannelServer`: a socket-based server that accepts remote channel connections
  and applies a transform function to incoming event DataFrames.
- `ChannelClient`: a client that connects to a remote channel server and
  sends/receives events.
- `RemoteChannelService`: a service wrapper that delegates to a remote server,
  allowing remote transforms to be mounted in a `ServiceNamespace`.
- `run_remote_pipeline`: utility function to run events through a sequence of
  remote servers.

Why this is the right step:
- Enables distributed pipeline execution where services run on separate nodes.
- Extends the Limbo-style channel model to a true distributed setting.
- Uses a simple, lightweight socket protocol for easy deployment.
- Maintains compatibility with the existing `ServiceNamespace` abstraction.

## Suggested future extensions

1. Add TLS/authentication layer to `ChannelServer` for secure remote execution.
2. Add service discovery mechanism for dynamic distributed pipelines.
3. Integrate trace serialization directly into `HybridRuntime` for automatic audit logging.
4. Add batching support to `ChannelClient` for improved throughput.
5. Add gRPC or HTTP/2 transport option for better interoperability.
