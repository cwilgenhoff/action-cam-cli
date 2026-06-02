### **ADR 0003: GPX Telemetry Parsing and Overlay Pipeline**

**Status:** Approved
**Date:** June 2, 2026

**Context:**
The `action-cam-cli` concatenates and color-grades DJI Action 4 footage using a zero-loss hardware encoding pipeline. The next requirement is to overlay cycling speed telemetry captured by a Garmin Instinct v1 watch.

Standard GPX exports from Garmin do not reliably encode real-time speed in a standardized tag. Commercial telemetry tools require rendering through a GUI, forcing a double-compression of our 10-bit HEVC masters. We need a deterministic, programmatic way to generate a transparent telemetry layer injected directly into our existing FFmpeg filter graph.

**Decision:**
We will implement a telemetry generator within a new `src/action_cam_cli/telemetry/` domain, abiding by the dependency rules established in ADR 0002.

The implementation will follow a 4-phase architecture:

1. **Data Ingestion (No Proprietary Tags):** We will use the `gpxpy` library to parse standard GPX 1.1 files. Speed will be derived purely from the `lat`, `lon`, and UTC `time` attributes using the Haversine formula.
2. **Smoothing & Interpolation:** The extracted 1Hz speeds will be passed through a rolling average filter and linearly interpolated to match the video's exact framerate. This will be implemented in pure Python (no `pandas` or `scipy`).
3. **Alpha-Channel Rendering:** We will use `Pillow` to draw the telemetry text onto transparent frames matching the exact resolution of the source footage, piping them into a dedicated FFmpeg subprocess to encode a transparent `.mov` file.
4. **Pipeline Injection & UTC Sync:** * **Auto-Sync:** The pipeline will extract the video's UTC `creation_time` via `ffprobe` and align it with the GPX atomic timestamps automatically. A manual `--offset` flag will act only as a fine-tuning mechanism for camera clock drift.
   * **Domain Independence:** The `grading` domain will remain generic. It will accept an optional `overlay_path` and overlay it dynamically at input `[N]`. It will composite the overlay **after** the `lut3d` filter to prevent color-shifting the text. The top-level orchestrator (CLI) will handle generating the telemetry and passing the path to the grading module.

**Consequences:**
* **Positive (Zero-Loss Footage):** Telemetry is baked in during the single grading pass. The master footage is never double-compressed (though the overlay `.mov` is a lossless intermediate).
* **Positive (Color Accuracy):** Compositing post-LUT ensures the overlay UI retains exact hex colors.
* **Negative (2D Speed Limitations):** Haversine calculates 2D surface distance, ignoring 3D elevation drops. Visual speed will be highly accurate but may drift slightly from the real-time barometric watch display.

**Alternatives Considered:**
* **FFmpeg `drawtext` filter:** Rejected. Dynamically changing values per-frame using raw FFmpeg text filters is highly impractical and brittle.
* **Proprietary Garmin `<gpxtpx:speed>` tags:** Rejected. Unreliable across different devices and export methods.
* **`pandas` / `numpy` / `OpenCV`:** Rejected. Linear interpolation and basic text rendering do not justify importing massive data science or computer vision binaries (per `CLAUDE.md`).
