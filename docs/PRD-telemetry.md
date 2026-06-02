# Technical Specification: Telemetry Overlay Generator (`telemetry.py`)

> **Status:** Draft / Phase 1 implementation.

## 1. Summary

A standalone command-line utility to parse standard GPX 1.1 tracking files, calculate movement speed directly from geospatial coordinates, and render a transparent alpha-channel video overlay (`.mov`). This tool generates a minimalist, frame-accurate speed gauge designed to be overlaid onto DJI Action 4 footage using FFmpeg.

## 2. Motivation

Standard Garmin Instinct v1 GPX exports do not reliably encode real-time speed in a standardized tag. Commercial telemetry tools are expensive, bloated with gamified dials, and require exporting a fully merged video, resulting in unacceptable double-compression of the master 10-bit HEVC footage. This tool provides a programmatic, lightweight method to generate an alpha-channel overlay that can eventually be injected into an existing zero-loss FFmpeg encoding pipeline.

## 3. Technical Architecture

* **Core Language:** Python 3.10+ (using standard type hinting).
* **Data Parsing:** `gpxpy` for reading the XML tree.
* **Math & Smoothing:** `scipy` or `pandas` (for 1Hz to 25fps interpolation and rolling averages).
* **Frame Generation:** `Pillow` (PIL) or `OpenCV` to draw text onto transparent canvas arrays.
* **Encoding Engine:** `ffmpeg` via Python `subprocess` (to encode the frames into a transparent video file).
* **Output Codec:** Apple ProRes 4444 (`prores_ks` with `pix_fmt yuva444p10le`) or PNG codec (`vcodec png` with `pix_fmt rgba`) to perfectly preserve the alpha transparency channel.

## 4. Core Features & Logic

### 4.1 Coordinate-Based Speed Calculation

The script must not rely on proprietary Garmin XML extensions (`<ns3:TrackPointExtension>`). It must calculate speed manually:

1. Extract the UTC `time`, `lat`, and `lon` for every `<trkpt>`.
2. Use the **Haversine formula** to calculate the distance (in meters) between consecutive points.
3. Divide by the time delta to calculate meters-per-second, then convert to kilometers-per-hour (km/h).

### 4.2 Smoothing & Framerate Interpolation

* **Rolling Average:** Apply a rolling average (e.g., a 3 to 5-second window) to the calculated speeds to eliminate erratic GPS bounce.
* **Interpolation:** GPX data is recorded at 1Hz (1 sample per second). The target video is 25 FPS. The script must interpolate the 1Hz data points into 25 smooth data points per second using a linear or cubic spline so the on-screen numbers transition smoothly rather than ticking once per second.

### 4.3 Minimalist Visual Design

Generate a 4K resolution (3840x2160) transparent canvas.

* Place the text in the lower-left or lower-right third.
* **Typography:** Use a clean, modern, easily readable sans-serif font (e.g., Arial, Roboto, or a system default).
* **Styling:** The text must be white, accompanied by a dark drop-shadow or a thick black stroke. This is critical for legibility against bright skies or white gravel roads.
* **Format:** Render the integer value with one decimal point and the unit (e.g., "24.5 km/h").

## 5. CLI Interface / UX

The script should use `argparse` to accept the following arguments:

* `input_gpx` (Required): Path to the `.gpx` file.
* `--fps`: Target framerate for the output video (Default: 25).
* `--offset`: An integer representing seconds to shift the telemetry data forward or backward to sync with camera drift (Default: 0).
* `--duration`: An optional limit in seconds to render (useful for generating a 5-minute overlay to match a test clip rather than rendering a 3-hour file).
* `-o`, `--output`: Path for the generated `.mov` file.

## 6. Edge Cases & Design Decisions

* **No GPU Acceleration Required:** Because the frames are essentially blank transparent canvases with a few lines of text, CPU rendering via Pillow/OpenCV piped directly to a CPU FFmpeg encoder is perfectly acceptable and highly portable.
* **Time Syncing:** The script assumes the start time of the GPX track loosely matches the start time of the video. The `--offset` flag is the sole mechanism for the user to manually correct camera clock drift.
* **Missing Elevation:** While the GPX contains elevation data (`<ele>`), this V1 implementation will ignore it to focus strictly on perfecting the speed calculation and video transparency pipeline.
