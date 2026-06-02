# Technical Specification: Telemetry Overlay Pipeline

> **Status:** Draft / Phase 1 implementation.

## 1. Summary
A programmatic pipeline to parse standard GPX 1.1 files, calculate movement speed from geospatial coordinates, and render a transparent alpha-channel video overlay (`.mov`). This gauge is injected into the DJI Action 4 FFmpeg pipeline, utilizing UTC timestamp matching to automatically sync the data to the video.

## 2. Technical Architecture
* **Core Language:** Python 3.10+ (using standard type hinting).
* **Data Parsing:** `gpxpy` for reading the XML tree.
* **Math & Smoothing:** Pure Python `math` (Haversine formula, linear interpolation, rolling average). No `pandas` or `numpy`.
* **Frame Generation:** `Pillow` (PIL) to draw text onto transparent canvas arrays. No `OpenCV`.
* **Encoding Engine:** `ffmpeg` via Python `subprocess` (encoding to ProRes 4444 or PNG codec for alpha transparency).

## 3. Core Features & Logic

### 3.1 Coordinate-Based Speed Calculation
1. Extract the UTC `time`, `lat`, and `lon` for every `<trkpt>`.
2. Use the **Haversine formula** to calculate distance between consecutive points.
3. Calculate km/h based on the time delta.

### 3.2 Smoothing & Framerate Interpolation
* **Rolling Average:** Apply a ~3-second moving window to absorb erratic GPS bounce.
* **Interpolation:** Linearly interpolate the 1Hz GPX data to match the dynamic framerate of the video (e.g., 25, 30, or 60 FPS) provided by `core.probe.probe_video_params`.

### 3.3 UTC Auto-Sync
The pipeline must extract the `creation_time` of the first clip in the video session using `core.probe`. It will find the exact matching UTC timestamp in the GPX array and crop the telemetry data to match the video perfectly.

### 3.4 Minimalist Visual Design
* **Dynamic Resolution:** Canvas size must match the source video (e.g., 3840x2160) exactly.
* **Styling:** White sans-serif text with a dark drop-shadow/stroke for legibility. 
* **Format:** Integer with one decimal point (e.g., "24.5 km/h").

## 4. Pipeline Injection (Filter Graph)
To prevent the Rec.709 LUT from altering the white UI text, the telemetry overlay must be applied **after** the color grade. The filter graph in `grading/ffmpeg.py` must be updated to support an optional `[N:v]` input (where `N` is the dynamically calculated index of the overlay file).
* **Graph Flow:** `Concat [vc]` -> `lut3d [graded]` -> `overlay [graded] + [telemetry]` -> `[vout]`.

## 5. CLI Interface
Add the following to `action_cam_cli/cli.py`:
* `--telemetry <path.gpx>`: Triggers the telemetry generation and injection.
* `--offset <seconds>`: An optional integer to manually nudge the UTC sync forward/backward to account for camera clock drift (Default: 0).