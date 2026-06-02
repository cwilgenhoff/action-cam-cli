# Technical Specification: DJI Action 4 Merge & Grade Pipeline

> **Status:** Implemented (as-built). This document reflects the final behavior of
> `merge_grade.py`. See [README.md](README.md) for install/usage.

## 1. Summary

A command-line utility to automate the ingestion of DJI Action 4 HEVC video files
from a target directory. The tool resolves the camera's 25-minute recording limit
by grouping the chunked files into continuous **recording sessions** (using the
sequential counter in each filename), concatenating each session seamlessly, and
applying a 3D LUT (`luts/dji-action-4.cube`) to convert the flat D-Log M (10-bit)
footage into a Rec.709 color-space master file. Each session produces its own
master, so a directory containing several independent recordings yields one graded
file per recording.

## 2. Motivation

The DJI Action 4 automatically splits long recordings into multiple files
(chaptering) approximately every 25 minutes due to file-system limitations. When
shooting in D-Log M to preserve dynamic range, manually stitching these chapters
and applying base color correction in an NLE is highly inefficient. This automated
script eliminates that friction by rendering a single, color-corrected master file
per session, ready for viewing or archive.

## 3. Technical Architecture

* **Core Language:** Python 3.10+ (uses `X | None` annotations and dataclasses).
* **Engine:** `ffmpeg` and `ffprobe` (via Python `subprocess`, list-form, no shell).
* **Target Platform:** Native **Windows** is the primary target (chosen to avoid
  WSL2 VHD bloat when processing ~16 GB source files); macOS/Linux also supported.
  Paths are handled cross-platform via `pathlib`, and the `lut3d` filter path is
  escaped for ffmpeg's filtergraph parser on Windows (drive-letter colon escaped,
  backslashes converted to forward slashes).
* **Input Format:** MP4 (HEVC/H.265, 10-bit color depth, D-Log M).
* **Asset Management:** LUTs are strictly organized in a local `luts/` directory,
  resolved relative to the script file's location (`Path(__file__).parent`).
* **Hardware Acceleration:** The encoding pipeline uses `hevc_nvenc` to leverage
  local NVIDIA RTX acceleration (e.g., RTX 4070). Decoding and the `lut3d` filter
  run on the CPU (uncompressed 10-bit frames buffered in system RAM), then frames
  are handed to the NVENC encoder — `lut3d` is a CPU filter, so frames are
  intentionally *not* kept in GPU memory.

## 4. Requirements

### 4.1. Functional Requirements

* **Ingestion:** Accept a target directory containing the raw `.mp4`/`.MP4` files
  as a CLI argument. `.LRF` low-res proxy files are strictly ignored, as are any
  other non-`.mp4` files. `.mp4` files that do not match the DJI naming convention
  are logged and skipped.
* **Filename Parsing & Session Grouping (Critical):** The script parses the DJI
  naming convention `DJI_YYYYMMDDHHMMSS_XXXX_D.MP4`, extracting the datetime stamp
  and the 4-digit sequential counter (`XXXX`). Files are grouped into recording
  **sessions** by consecutive counters: a perfectly consecutive run (e.g. 0012,
  0013, 0014) is one continuous recording; any break in the sequence starts a new
  session. Files within a session are ordered by counter. This filename-based
  approach is preferred over `ffprobe` `creation_time` / OS modification times
  because it survives copies across file systems and is deterministic.
* **LUT Application:** Automatically locate and apply the color profile at
  `luts/dji-action-4.cube` (relative to the script file's location).
* **Concatenation:** Merge each session's files seamlessly via the `concat` filter,
  carrying both video and audio (`v=1:a=1`) so audio tracks are preserved without
  de-sync at the stitching points.
* **Output:** Produce one `.mp4` per session in the source directory (or a
  specified output directory), named `[EarliestTimestamp]_merged_graded.mp4`,
  where the timestamp is the 14-digit stamp of the session's earliest clip.

### 4.2. Non-Functional Requirements

* **Performance:** CPU-only encoding is prohibited. The FFmpeg command prioritizes
  NVENC (`-c:v hevc_nvenc`). Decode + `lut3d` run on CPU/RAM by design (see §3).
* **Resilience:** The script aborts early (before any encode) with a clear error if
  `ffmpeg`/`ffprobe` are missing, if `luts/dji-action-4.cube` is missing, or if no
  DJI clips are found. Per session, a resolution/framerate mismatch causes that
  session to be skipped with a warning while other sessions continue. ffmpeg's own
  output is suppressed unless an error occurs.
* **Portability:** Windows-first, but cross-platform (`pathlib`, list-form
  subprocess, platform-aware filtergraph path escaping).
* **Interruption:** `Ctrl+C` gracefully terminates the running ffmpeg process and
  deletes the incomplete output file (no zombie encoder, no partial artifacts).

## 5. Implementation Plan (Completed)

### Phase 1: Environment & Directory Setup

* `argparse` CLI: `input_dir` (positional), `-o/--output-dir` (optional),
  `-f/--force` (overwrite existing outputs), `--dry-run` (print commands, no encode).
* Dependency checks for `ffmpeg` and `ffprobe` on `PATH`.
* Validate existence of `luts/dji-action-4.cube` before proceeding.
* Validate the input directory and create the output directory if needed.

### Phase 2: Filename Parsing & Session Grouping

* Scan the input directory for `.mp4`/`.MP4` files; ignore `.LRF` proxies.
* Parse each filename with regex `^DJI_(\d{14})_(\d{4})_D\.mp4$` (case-insensitive)
  into a `Clip` dataclass (path, counter, parsed datetime, raw stamp). Non-matching
  `.mp4` files are warned and skipped.
* Sort clips by counter and group into sessions on consecutive-counter runs.

### Phase 3: FFmpeg Filter Graph & Command Construction

* **Per-session validation:** Use `ffprobe` to confirm all clips in a session share
  identical resolution and `r_frame_rate`. On mismatch, skip that session (with a
  precise warning) and continue with the others.
* **Concatenation Strategy:** Because a video filter (`lut3d`) is applied, stream
  copying (concat demuxer) cannot be used — the script decodes, filters, re-encodes.
* Build the complex filter graph dynamically based on the number of clips:
  ```
  [0:v][0:a][1:v][1:a]…concat=n=N:v=1:a=1[vc][ac];
  [vc]lut3d=file=<escaped luts/dji-action-4.cube>[vout];
  [ac]bass=g=-6:f=150[aout]
  ```
* **Audio Processing:** The DJI Action 4 internal mic suffers from excessive
  low-frequency bass. A low-shelf cut (`bass=g=-6:f=150`) is applied to the
  concatenated audio stream inside the filter graph (mapped via `[aout]`).
* **Windows path safety:** the LUT path is escaped for the filtergraph parser
  (`C:\luts\x.cube` → `C\:/luts/x.cube`).

### Phase 4: Hardware-Accelerated Execution & UX

* Execute via `subprocess.Popen` (list-form). `--dry-run` instead prints the full
  command to stdout (via `shlex.join`) and skips execution.
* **Required FFmpeg output flags:**
* `-c:v hevc_nvenc` (Hardware HEVC encoder)
* `-preset p6` (High-quality NVENC preset)
* `-cq 19` (Constant Quality target)
* `-pix_fmt p010le` (Crucial: maintain 10-bit color depth; `p010le` is the
  NVENC-compatible 10-bit format, not the CPU-side `yuv420p10le`)
* `-c:a aac -b:a 320k` (High-quality audio re-encoding)
* **Overwrite handling:** without `--force`, a session whose output already exists
  is skipped; with `--force`, `-y` is appended to overwrite.
* **Progress UX:** the command includes `-progress pipe:1` (and quiet logging); the
  script parses `out_time_us`/`out_time_ms` from stdout to drive a `tqdm` progress
  bar. `tqdm` is optional — a plain percentage fallback is used if it isn't
  installed. ffmpeg's stderr is captured and shown only on a non-zero exit.
* **Graceful termination:** `KeyboardInterrupt` terminates ffmpeg (TERM → 5s grace
  → kill), removes the partial output, stops remaining sessions, and exits 130.

## 6. Edge Cases & Design Decisions

* **Framerate/Resolution Mismatches:** Validated per session via `ffprobe`. A
  mismatch within a session skips *that session only* (with a warning) and
  continues processing the remaining sessions — the whole run is **not** aborted.
* **Orphaned / non-contiguous files:** Handled implicitly by sequence-counter
  grouping — a break in the counter sequence starts a new session and therefore a
  separate output file. The earlier-considered alternatives (grouping by calendar
  day, or a ">1-minute time-gap" heuristic) were **deliberately not implemented**:
  the sequence counter is a more robust and deterministic signal, and avoiding the
  heuristic keeps the architecture clean.
* **Proxies & foreign files:** `.LRF` proxies and non-DJI-named files are ignored;
  non-conforming `.mp4` files are warned and skipped rather than aborting the run.
* **Audio stream presence:** DJI firmware is deterministic and always writes an
  audio stream, so the `a=1` concat assumes audio exists (no extra probe by design).
