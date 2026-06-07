# Technical Specification: Telemetry Overlay Pipeline

> **Status:** Draft / Phase 1 implementation. Speed source: Garmin **TCX** (see ADR 0003).

## 1. Summary
A programmatic pipeline to parse a Garmin **TCX** export, read the device-measured
speed per track point, and render a transparent alpha-channel video overlay (`.mov`).
This gauge is injected into the DJI Action 4 FFmpeg pipeline, using UTC timestamp
matching to automatically sync the data to the video.

## 2. Technical Architecture
* **Core Language:** Python 3.10+ (standard type hinting).
* **Data Parsing:** Standard-library `xml.etree.ElementTree` (TCX is XML — no third-party parser).
* **Math & Smoothing:** Pure Python (time-based rolling average + linear interpolation). No `pandas`/`numpy`.
* **Frame Generation:** `Pillow` (PIL) to draw text onto transparent canvases. No `OpenCV`.
* **Encoding Engine:** `ffmpeg` via Python `subprocess` (ProRes 4444 or PNG codec for alpha).

## 3. Core Features & Logic

### 3.1 Device Speed (from TCX)
The Garmin TCX records the device's measured speed (GPS Doppler — what the watch
displays), far more accurate for instantaneous values than re-deriving from coordinates.

1. For each `<Trackpoint>`, read `<Time>` (UTC) and `<ns3:Speed>` (m/s) from the
   ActivityExtension namespace.
2. Convert m/s → km/h.
3. Track points without a speed value are skipped (interpolated over downstream).

### 3.2 Smoothing & Framerate Interpolation
Garmin "smart recording" yields **irregular intervals** (observed ~1–13 s on the
Instinct v1), so all math is **time-based**, keyed on each point's UTC timestamp.

* **Rolling Average:** time-based moving window (~3 s) to absorb residual jitter.
* **Interpolation:** linearly interpolate the per-point speeds **by timestamp** onto the
  video's frame grid (fps from `core.probe.probe_video_params`, e.g. 25/30/60).

### 3.3 UTC Auto-Sync
Extract the `creation_time` of the first clip in the session via `core.probe`, align it
to the TCX timestamps, and crop the telemetry to the video window. `--offset` is a manual
fine-tune for camera clock drift.

### 3.4 Minimalist Visual Design
* **Dynamic Resolution:** canvas matches the source video exactly.
* **Styling:** white sans-serif text with a dark drop-shadow/stroke for legibility.
* **Format:** one decimal place and unit (e.g. "24.5 km/h").

## 4. Pipeline Injection (Filter Graph)
The overlay is composited **after** the Rec.709 LUT (so the LUT can't alter the white UI).
`grading/ffmpeg.py` gains an optional `[N:v]` overlay input (N = dynamically calculated index).
* **Graph Flow:** `concat [vc]` → `lut3d [graded]` → `overlay [graded] + [telemetry]` → `[vout]`.

## 5. CLI Interface
Add to `action_cam_cli/cli.py`:
* `--telemetry <path.tcx>`: triggers telemetry generation and injection.
* `--offset <seconds>`: optional manual nudge for camera clock drift (Default: 0).
