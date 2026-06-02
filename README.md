# DJI Action 4 Merge & Grade Pipeline

A CLI utility that ingests chunked DJI Action 4 HEVC (D-Log M, 10-bit) clips,
groups them into continuous recording sessions by their filename sequence
counter, concatenates each session seamlessly, applies the
`luts/dji-action-4.cube` 3D LUT to convert D-Log M → Rec.709, and renders one
NVENC-accelerated master `.mp4` per session.

See [PRD.md](PRD.md) for the full technical specification.

## Requirements

- Python 3.10+ (native Windows is the primary target; macOS/Linux also work)
- FFmpeg + FFprobe on `PATH` (an `hevc_nvenc`-capable build)
- An NVIDIA GPU with NVENC (e.g. RTX 4070)
- `luts/dji-action-4.cube` present (the Rec.709 conversion LUT)

Optional Python deps (nicer progress bar via `tqdm`; the tool falls back to
plain percentage logging if it isn't installed):

```powershell
# Windows (PowerShell / cmd):
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
# macOS / Linux:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

On Windows use `python` (or `py`); on macOS/Linux use `python3`.

```powershell
# Merge all sessions in a directory, writing each master back into it
python merge_grade.py "D:\DJI\clips"

# Write masters to a separate output directory
python merge_grade.py "D:\DJI\clips" -o "D:\DJI\masters"

# Overwrite existing output files instead of skipping them
python merge_grade.py "D:\DJI\clips" --force

# Validate sessions and print the ffmpeg command(s) without encoding
python merge_grade.py "D:\DJI\clips" --dry-run
```

`--dry-run` writes each constructed command to **stdout** (progress/status go to
stderr), so you can inspect or capture it before committing to a multi-GB render:

```powershell
python merge_grade.py "D:\DJI\clips" --dry-run > commands.txt
```

Each continuous recording session (consecutive sequence counters) becomes one
`[EarliestStamp]_merged_graded.mp4`. A live progress bar is shown per session;
press **Ctrl+C** to abort — the running ffmpeg encoder is terminated and the
incomplete output file is deleted.

## Implementation status

- [x] **Phase 1** — CLI, dependency checks, LUT validation
- [x] **Phase 2** — Clip discovery, filename parsing, session grouping by sequence counter
- [x] **Phase 3** — Per-session ffprobe validation, filter graph & ffmpeg command construction
- [x] **Phase 4** — NVENC execution, progress UX (tqdm), graceful Ctrl+C termination & cleanup
