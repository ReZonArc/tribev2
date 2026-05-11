# TRIBE v2 Codebase Explanation + Unconventional Extension Directions

## What this repository is

TRIBE v2 is a multimodal brain-encoding system: it predicts fMRI activity from video/audio/text stimuli.  
Core idea: extract rich representations from pretrained modality models, fuse them in a transformer, and map to cortical outputs.

## High-level structure

- `tribev2/model.py`
  - Core trainable model (`FmriEncoderModel`)
  - Per-modality projectors, fusion, transformer encoder, subject-aware output layers
- `tribev2/main.py`
  - Experiment orchestration (`TribeExperiment`)
  - Connects datasets, transforms, feature extractors, training/eval flow
- `tribev2/pl_module.py`
  - PyTorch Lightning wrapper for optimization, metrics, loss
- `tribev2/demo_utils.py`
  - User-facing inference API (`TribeModel.from_pretrained`, `get_events_dataframe`, `predict`)
- `tribev2/eventstransforms.py`
  - Event pipeline transforms (audio extraction, transcription, chunking, dedup, splitting)
- `tribev2/studies/`
  - Dataset adapters (Algonauts2025, Lahner2024, Lebel2023, Wen2017)
- `tribev2/grids/`
  - Default configs and grid launch scripts for local/slurm runs
- `tribev2/plotting/`
  - Surface/brain visualization helpers
- `tribev2/utils_fmri.py`
  - fMRI template-space utilities and surface projection helpers

## Key technologies

- Python 3.11+
- PyTorch + PyTorch Lightning
- x_transformers
- neuralset / neuraltrain
- HuggingFace model ecosystem
- pandas / numpy
- nilearn / nibabel (optional plotting/training extras)
- Slurm-oriented infra configuration via `exca` patterns in configs

## Organization pattern

The project is intentionally **config-driven**:
- Feature extraction setup, study list, transforms, and model hyperparameters are declared in config dictionaries (`grids/defaults.py`).
- The same conceptual pipeline supports both:
  - easy inference from files (`TribeModel`)
  - large-scale training/grid experiments (`TribeExperiment` + grid scripts)

The shared bridge is the **events dataframe** abstraction (typed, timestamped multimodal events).

## Unconventional extension ideas

### 1) Maude / term-rewriting angle

Best fit in this repository:
- Event transforms are already rewrite-like stages (e.g., Audio -> Word/Text enriched events)
- A term-rewriting representation could formalize correctness/normalization of event pipelines

Near-term value:
- formal event normalization contracts
- explicit rewrite rules for reproducibility and auditability

### 2) 9P file-server angle (e.g., diod style interface)

Best fit in this repository:
- expose model inference and cached features as a virtual filesystem namespace
- treat inputs, events, and outputs as files for composable tooling

Near-term value:
- process-agnostic integration with other systems
- clean remote-serving model for prediction jobs

### 3) Limbo / Inferno-style distributed namespace

Best fit:
- run event and feature stages as channel-based distributed services
- mount and compose prediction services across nodes

Near-term value:
- strong separation of concerns in distributed pipeline
- elegant namespace-based orchestration for multimodal services

### 4) Hybrid DSL (Maude semantics + Limbo-style execution)

Best fit:
- formal rewrite semantics for transformations/config state
- distributed operational runtime for execution and serving

Near-term value:
- explicit semantics + practical distributed execution model

---

## Initial practical implementation chosen now

For low-risk, high-leverage first steps, this repository now includes a minimal **experimental rewriting scaffold** (`tribev2.experimental.rewrite`) to:

- represent event transformations as explicit rewrite rules,
- run them as a deterministic pipeline over pandas event frames,
- serve as a bridge toward future Maude-style formalization.

See:
- `tribev2/experimental/rewrite.py`
- `docs/unconventional_runtime_initial_steps.md`
