### **ADR 0003: Telemetry Parsing and Overlay Pipeline**

**Status:** Approved
**Date:** June 2, 2026
**Amended:** June 2, 2026 — speed source changed from GPX/Haversine to Garmin **TCX device speed** after verifying against a real ride (see *Alternatives Considered*).

**Context:**
The `action-cam-cli` concatenates and color-grades DJI Action 4 footage using a zero-loss hardware encoding pipeline. The next requirement is to overlay cycling speed telemetry captured by a Garmin Instinct v1 watch.

Commercial telemetry tools require rendering through a GUI, forcing a double-compression of our 10-bit HEVC masters. We need a deterministic, programmatic way to generate a transparent telemetry layer injected directly into our existing FFmpeg filter graph.

We initially planned to parse GPX 1.1 and derive speed from coordinates (Haversine). Verifying against the real ride disproved that for *instantaneous* speed (see *Alternatives Considered*), so we ingest the Garmin **TCX** export, which carries the device's own measured speed.

**Decision:**
We will implement a telemetry generator within a new `src/action_cam_cli/telemetry/` domain, abiding by the dependency rules established in ADR 0002.

1. **Data Ingestion (TCX device speed):** Parse the Garmin **TCX** (Training Center XML) export with the standard library (`xml.etree.ElementTree`) — *no third-party parser*. Read the device-measured `<ns3:Speed>` (m/s) per `<Trackpoint>` directly, rather than deriving speed from coordinates. This matches the speed Garmin Connect and the watch report.
2. **Smoothing & Interpolation:** Track points arrive at irregular intervals (Garmin "smart recording"), so per-point speeds are passed through a *time-based* rolling average and linearly interpolated to the video's framerate. Pure Python (no `pandas`/`numpy`).
3. **Alpha-Channel Rendering:** Use `Pillow` to draw the telemetry text onto transparent frames matching the exact resolution of the source footage, piped into an FFmpeg subprocess to encode a transparent `.mov`.
4. **Pipeline Injection & UTC Sync:**
   * **Auto-Sync:** Extract the video's UTC `creation_time` via `ffprobe` and align it with the TCX timestamps automatically; a manual `--offset` flag fine-tunes camera clock drift.
   * **Domain Independence:** `grading` stays generic — it accepts an optional `overlay_path`, composited at input `[N]` **after** the `lut3d` filter (so the LUT can't color-shift the text). The top-level CLI orchestrator generates the telemetry and passes the path to grading.

**Consequences:**
* **Positive (Zero-Loss Footage):** Telemetry is baked in during the single grading pass; the master is never double-compressed (the overlay `.mov` is a lossless intermediate).
* **Positive (Color Accuracy):** Compositing post-LUT preserves the overlay's exact colors.
* **Positive (Device-Accurate Speed):** Using the watch's recorded speed means the gauge matches Garmin Connect exactly (verified: max 36.4 km/h, vs 39.1 for the rejected Haversine approach).
* **Negative (Garmin-Specific Input):** TCX is a Garmin/Training-Center format; a non-Garmin source would need a different ingester — acceptable for this Garmin + DJI pipeline.

**Alternatives Considered:**
* **GPX 1.1 + Haversine (coordinate-derived speed):** Rejected. Verified against the real 67-min ride: distance and averages were accurate (21.13 km, 18.9 km/h), but instantaneous speed **overshot** (max 39.1 vs the device's 36.4 km/h) because deriving speed from GPS position amplifies positional jitter — and the overlay is a live gauge where that peak error is visible.
* **FIT (binary) via `fitparse`:** Rejected. Device-accurate, but requires a binary-format parser dependency. TCX delivers the same device speed as plain XML via the standard library — same accuracy, no new dependency.
* **FFmpeg `drawtext` filter:** Rejected. Per-frame changing values are impractical/brittle with raw text filters.
* **Proprietary Garmin `<gpxtpx:speed>` tags in GPX:** Rejected. Unreliable across devices/export methods (and superseded by the TCX decision).
* **`pandas` / `numpy` / `OpenCV`:** Rejected. Linear interpolation and basic text rendering don't justify importing heavy binaries (per `CLAUDE.md`).
