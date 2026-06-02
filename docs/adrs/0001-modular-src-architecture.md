### **ADR 0001: Migration to Modular `src/` Package Architecture**

**Status:** Accepted (implemented 2026-06-02)
**Date:** June 2, 2026

**Context:**
The `action-cam-cli` project originated as a single-file script (`merge_grade.py`) designed to solve a specific friction point: concatenating chaptered DJI Action 4 HEVC files and applying a Rec.709 color-grading LUT via hardware-accelerated FFmpeg.

As the project proved successful, requirements expanded to include extracting GPX telemetry data from a Garmin Instinct v1 to generate visual speed overlays. Continuing to build inside a flat, single-file script would tangle the dependency graph and make it difficult to share generic utilities between the grading pipeline and the upcoming telemetry pipeline.

Furthermore, relying on a raw `requirements.txt` and calling the script directly via `python merge_grade.py` creates fragile path-resolution issues for static assets (like the `.cube` LUT file) depending on the user's current working directory.

**Decision:**
We will refactor the codebase from a flat, single-script structure into a modern Python package using the `src/` layout. *This ADR covers the packaging, entry point, and asset strategy only; the internal decomposition of the business logic into single-responsibility modules is addressed separately in ADR 0002.*

1. **Dependency & Entry Point Management:** We will replace `requirements.txt` with `pyproject.toml`. The application will be installable locally (`pip install -e .`), exposing a global CLI command (`action-cam = action_cam_cli.cli:main`).
2. **Package Skeleton:** Code moves under `src/action_cam_cli/`, organized into:
   * `cli.py`: argparse configuration and routing.
   * `core/`: shared infrastructure usable by any pipeline (initially `config.py`).
   * `grading/`: the merge-and-grade pipeline (initially the consolidated `merge_grade.py`).

   Finer module-level decomposition of `grading/merge_grade.py` is intentionally deferred to **ADR 0002**.
3. **Asset Management:** Non-code assets, specifically the Rec.709 `.cube` LUT, are moved out of the source tree into a top-level `assets/luts/` directory. Path resolution in `core/config.py` locates these assets relative to the package, ensuring stability regardless of execution directory.

**Consequences:**

* **Positive:** The architecture is now scalable. A future `telemetry/` domain can import utilities from `core/` without creating circular dependencies with `grading/`.
* **Positive:** The developer and user experience improves. Installing via `pyproject.toml` automatically handles dependencies like `tqdm` and provisions the `action-cam` command within the virtual environment.
* **Negative:** Increased structural boilerplate — multiple `__init__.py` files and import discipline replace a single readable script.
* **Negative (assumption):** Asset resolution is package-relative (`Path(__file__)` traversal), which assumes an editable/source layout; a standard wheel build would not include the top-level `assets/` directory. This assumption is carried forward and made explicit in ADR 0002.

**Follow-up:** ADR 0002 decomposes the remaining `grading/merge_grade.py` monolith into single-responsibility modules and establishes the dependency invariant that keeps the architecture acyclic.
