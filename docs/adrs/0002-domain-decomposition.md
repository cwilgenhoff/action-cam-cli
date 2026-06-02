### **ADR 0002: Domain Decomposition of the `merge_grade.py` Monolith**

**Status:** Accepted
**Date:** June 2, 2026

**Context:**
Following the successful migration to the `src/` layout package architecture (ADR 0001), our application is cleanly packaged and asset resolution is stable via editable installs (`pip install -e .`). However, the actual business logic remains trapped in a 500+ line "God Module" (`grading/merge_grade.py`).

This single file conflates CLI routing, file discovery, metadata probing, FFmpeg string construction, and subprocess execution. Furthermore, it aggressively uses `sys.exit()` for error handling, preventing it from acting as a consumable library, and it lacks automated testing for our most critical asset: the optimized FFmpeg encoding strings.

As we prepare to introduce the new GPX Telemetry feature, we must extract shared utilities (like `ffprobe` wrappers) so both domains can use them. If we do not decompose the monolith now, we risk either duplicating code or tangling the dependency graph between the `grading` and `telemetry` features.

**Decision:**
We will decompose `merge_grade.py` into distinct, single-responsibility modules divided between `core` (shared infrastructure) and `grading` (feature logic), governed by strict architectural rules.

**1. The Dependency Invariant**

* `core/` is a leaf node. It may import standard libraries or external dependencies, but **never** internal project modules.
* Feature domains (`grading/` and the upcoming `telemetry/`) may depend on `core/`.
* Feature domains may **never** depend on each other.

**2. Target Architecture**

```text
tests/                 # New: Pytest suite
  └── test_ffmpeg.py   # Pure builder tests locking the encoding flags
src/action_cam_cli/
  ├── __main__.py      # Enables `python -m action_cam_cli`
  ├── cli.py           # Argparse, routing, and exit-code translation (NO business logic)
  ├── core/
  │   ├── config.py    # Cross-cutting constants (paths, REQUIRED_BINARIES)
  │   ├── discovery.py # Generic filesystem scanning (thin wrappers)
  │   ├── errors.py    # Custom exception types (e.g. PipelineError)
  │   ├── models.py    # Data transfer objects (e.g. `Clip`)
  │   └── probe.py     # `ffprobe` wrappers (surfacing duration, resolution, AND creation_time)
  └── grading/
      ├── sessions.py  # DJI-specific grouping and regex parsing
      ├── ffmpeg.py    # Pure functions for filter graphs and command construction
      ├── executor.py  # Subprocess execution, progress bars, and Ctrl-C handling
      └── pipeline.py  # Orchestrator wiring the grading domain together
```

**3. Anti-God-Module Policies**

* **Domain Constants:** Constants specific to a domain (e.g., `NVENC_OUTPUT_ARGS`, `AUDIO_FILTER`, `DJI_NAME_RE`) must be moved out of `config.py` and into their respective domain files (`ffmpeg.py` and `sessions.py`).
* **Exception Bubbling:** `sys.exit()` is strictly banned in `core/` and `grading/`. Domain code will raise standard or custom exceptions (custom types living in `core/errors.py`); `cli.py` will catch them, print to `stderr`, and translate them to POSIX exit codes.
* **Testing:** We will add `pytest` as a dev dependency. We will write unit tests for `build_filter_graph` and `build_ffmpeg_command` to explicitly lock the encoding flags against accidental regressions.
* **Behavior Preservation:** This is a pure structural refactor — runtime behavior and, critically, the emitted FFmpeg command **must not change**. This is verified by capturing `action-cam --dry-run` output (the full command list, including input order, maps, filter graph, and output naming) before and after the refactor and confirming it is byte-for-byte identical. The unit tests above guard the builders; the dry-run diff guards the whole pipeline.

**Consequences:**

* **Positive:** The FFmpeg hardware strings are completely decoupled from `subprocess.Popen`, allowing us to execute pure, instant unit tests on our command builders.
* **Positive:** The refactor is *verifiably* behavior-preserving (builder unit tests + a before/after `--dry-run` command diff), directly satisfying the "FFmpeg integrity" invariant in `CLAUDE.md`.
* **Positive:** `probe.py` is proactively designed to extract video `creation_time`, which will perfectly unblock the UTC-sync requirement for the upcoming Telemetry feature.
* **Positive:** The architecture is strictly scaled. Telemetry can safely be added without circular dependencies.
* **Negative (Assumption Locked):** Because our asset resolution (the `.cube` file) relies on path traversal from the source code, we are explicitly assuming this tool will be run via editable installation (`pip install -e .`). A standard wheel build would drop the top-level `assets/` folder. This is an acceptable trade-off for an internal CLI tool.

**Alternatives Considered:**

* **Fake-Generic Abstraction:** Moving DJI filename parsing into `core/discovery.py` to "share" it. *Rejected:* DJI parsing is intrinsically tied to the grading/concatenation logic. Telemetry will parse `.gpx` files, not DJI `.mp4`s. Prematurely moving DJI logic to `core` pollutes the generic namespace.
* **Adding to the Monolith:** Building the telemetry pipeline directly into `merge_grade.py`. *Rejected:* Would result in a 1,000+ line unmaintainable script with completely entangled CLI flags and exception handling.
* **Refactoring without Tests:** Just moving the code. *Rejected:* The entire value proposition of separating `ffmpeg.py` from `executor.py` is testability. Without adding a test, the architectural overhead is unjustified.
