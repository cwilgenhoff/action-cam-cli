# action-cam-cli

**Turn a folder of raw DJI Action 4 clips into finished, color-graded videos — automatically.**

## The problem

Two things make DJI Action 4 footage tedious to deal with before you can actually
watch or share it:

1. **Long recordings come out in pieces.** To work around file-size limits, the
   camera splits anything longer than ~25 minutes into multiple "chapter" files.
   A single 40-minute ride is really two or three separate `.mp4` files that have
   to be stitched back together in the right order.
2. **D-Log M footage looks flat and washed out.** Shooting in D-Log M preserves
   dynamic range for editing, but straight off the camera it's grey and
   low-contrast. It needs a color conversion (a LUT) into a normal Rec.709 look
   before it's watchable.

Normally that means dragging every clip into a video editor, lining them up by
hand, dropping a LUT on each, and exporting — for every recording, every time.

## What it does

Point `action-cam` at a folder of clips and it handles all of that for you:

- **Figures out which clips belong to the same recording** (using the camera's
  sequence numbering) and produces one finished file per recording.
- **Stitches each recording back into one seamless file** — video and audio, no
  gaps or drift at the joins.
- **Applies the D-Log M → Rec.709 color conversion** so the result looks right
  out of the box.
- **Cleans up the audio**, taming the Action 4 mic's boomy low end.
- **Renders fast on your GPU** (NVIDIA NVENC), keeping the original 10-bit color.

The result: one ready-to-watch `.mp4` per recording, named by its timestamp — no
editor, no manual sorting, batch-friendly.

## Getting started

### Prerequisites

- An **NVIDIA GPU** with NVENC (e.g. RTX 4070) — encoding is GPU-accelerated and
  **required**. The tool checks NVENC up front and aborts with a clear message if
  it's unavailable. (`--dry-run` needs no GPU — it only prints the planned commands.)
- **FFmpeg** (a build that includes `hevc_nvenc`) available on your `PATH`.
  Verify it's there:
  - Windows: `ffmpeg -hide_banner -encoders | findstr nvenc`
  - macOS/Linux: `ffmpeg -hide_banner -encoders | grep nvenc`
- **Python 3.10+**. Native Windows is the primary target; macOS/Linux also work.

### Install

From the project folder:

```powershell
# Windows (PowerShell)
py -m venv .venv
.venv\Scripts\activate
pip install -e .
```

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

That installs the `action-cam` command along with everything it needs (including
the progress bar).

### Use it

```powershell
# Grade every recording in a folder (writes the results back into it)
action-cam "D:\DJI\clips"

# Send the finished files to a separate folder
action-cam "D:\DJI\clips" -o "D:\DJI\masters"

# Overwrite existing results instead of skipping them
action-cam "D:\DJI\clips" --force

# Preview what would happen, without rendering anything
action-cam "D:\DJI\clips" --dry-run
```

Run `action-cam --help` for the full list of options.

### What to expect

- One file per recording, named `[timestamp]_merged_graded.mp4`.
- A live progress bar per recording. Press **Ctrl+C** to stop — the in-progress
  file is deleted automatically so you're never left with a half-rendered video.
- Proxy files (`.LRF`) and unrelated files are ignored. If the clips in one
  recording don't match (different resolution or frame rate), that recording is
  skipped with a warning and the rest still process.
- `--dry-run` prints the exact FFmpeg command(s) to **stdout** (status messages
  go to stderr), so you can inspect — or capture with `> commands.txt` — before
  committing to a multi-GB batch.

## Under the hood

The color conversion uses the 3D LUT shipped at
`assets/luts/dji-action-4.cube`. For the full technical specification, see
[docs/PRD-merge-grade.md](docs/PRD-merge-grade.md).

## Development

```bash
pip install -e ".[dev]"   # editable install with pytest
pytest                    # run the test suite
```

Architecture decisions are recorded as ADRs in [docs/adrs/](docs/adrs/).

## License

Released under the [GNU Affero General Public License v3.0 or later](LICENSE).
