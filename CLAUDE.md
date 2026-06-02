## 1. Project Context

**The Application:** `action-cam-cli` is a frictionless, automated video pipeline for DJI Action 4 cycling footage. It solves two problems: seamlessly concatenating the camera's ~25-minute file "chapters" back into whole recordings, and converting flat D-Log M footage to Rec.709 with a 3D LUT — producing one finished master per recording.

**Status: ACTIVE REFACTORING.** The single-file script has been moved into a `src/` package (`src/action_cam_cli/`, installed via `pip install -e .`, console script `action-cam`), but a **larger architectural refactor is planned before** the next feature, **GPX telemetry generation** (see `docs/PRD-telemetry.md`). Expect significant structural changes and file movements — **do not aggressively block architectural changes or file moves requested by the Lead Engineer.**

**Core Philosophy:**
* **Zero UI Friction:** dump the SD card, run one CLI command, and walk away. No manual NLE timeline syncing.
* **No Double Compression:** video is encoded exactly *once*, to preserve the 10-bit HEVC masters.
* **Hardware Symbiosis:** decode/filter on the CPU + RAM and encode on the GPU (RTX 4070 NVENC). This avoids round-tripping frames over the PCIe bus and keeps the CPU-only `lut3d` filter working.

## 2. Tech Stack (Summary)

* **Language:** Python 3.10+ (standard type hinting: `Path`, `list[str]`, `X | None`).
* **Packaging:** `src/` layout managed via `pyproject.toml` (installed locally via `pip install -e .`). Import package `action_cam_cli`; distribution name `action-cam-cli`; console script `action-cam`.
* **Video Engine:** `ffmpeg` and `ffprobe` invoked strictly via Python's `subprocess` (list-format only, absolutely NO `shell=True`).
* **Platforms:** Windows is the primary target (64 GB RAM, NVIDIA RTX 4070, `hevc_nvenc`). The code is cross-platform and also runs on macOS/Linux for development.
* **Dependencies (Minimalist):** `tqdm` only today (progress bar, with a plain-text fallback if it isn't installed). `gpxpy` is planned for the telemetry feature but **not yet added**. *Do not introduce heavy frameworks (Pandas, NumPy, OpenCV) unless explicitly approved.*

## 3. Mandatory Engineering Baselines

While full standard documents will be written later, agents MUST adhere to these baselines:

| Domain | Baseline Rule |
| --- | --- |
| **FFmpeg Integrity** | The filter graph (`concat` + `lut3d` + `bass=g=-6:f=150`) and hardware encode flags (`-c:v hevc_nvenc -preset p6 -cq 19 -pix_fmt p010le -c:a aac -b:a 320k`) are highly optimized. **Never alter encoding parameters, pixel format, or hardware flags** without explicit instruction. |
| **LUT Path Quoting** | The `lut3d` file path must stay **single-quoted with its drive-letter colon escaped** (`file='C\:/.../dji-action-4.cube'`). This is required for the Windows filtergraph parser — do not "simplify" the quoting or escaping. |
| **Asset Resolution** | Bundled assets (the LUT under `assets/`) are resolved **relative to the package** via `core.config`, never assumed to be in the current working directory. Do not reintroduce cwd-relative asset paths. |
| **CLI User Experience** | The tool runs unattended via `argparse`. Human status/progress goes to **stderr**; machine-readable output (e.g. `--dry-run` commands) goes to **stdout**. Errors must be cleanly caught and logged. |
| **Process Management** | `KeyboardInterrupt` (Ctrl+C) must gracefully terminate the underlying `ffmpeg` process **and delete the partial output file** before exiting, to prevent zombie GPU processes and half-rendered videos. |
| **Data Synchronization** | When aligning external data (like GPX telemetry) with video, rely strictly on UTC atomic timestamps. Never design manual visual syncing mechanisms. |
| **Version Control** | Use atomic, Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`). Commit only when asked. End each commit message with the appropriate `Co-Authored-By:` trailer. |

## 4. Documentation Map

Detailed technical specifications and planning artifacts live under `docs/`. Agents must consult the relevant PRD before implementing new modules:

* **Core Pipeline (as-built):** `docs/PRD-merge-grade.md`
* **Telemetry Generation:** `docs/PRD-telemetry.md` *(draft, in development)*
