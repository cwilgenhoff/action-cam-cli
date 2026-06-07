"""Encode rendered overlay frames into a transparent ``.mov``.

Pure command construction (``build_overlay_encode_cmd``) is separated from the
subprocess that streams frames (``render_overlay_mov``), so the command is
unit-testable without ffmpeg.
"""

import subprocess
from collections.abc import Iterable
from pathlib import Path

from action_cam_cli.core.errors import PipelineError
from action_cam_cli.telemetry.render import Size, render_frame


def build_overlay_encode_cmd(size: Size, fps: float, output_path: Path, force: bool = False) -> list[str]:
    """ffmpeg command to encode raw RGBA frames (piped on stdin) into a transparent
    ProRes 4444 ``.mov``. ``yuva444p10le`` carries the alpha channel through."""
    width, height = size
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error"]
    if force:
        cmd.append("-y")
    cmd += [
        "-f", "rawvideo",
        "-pixel_format", "rgba",
        "-video_size", f"{width}x{height}",
        "-framerate", str(fps),
        "-i", "-",
        "-c:v", "prores_ks",
        "-profile:v", "4444",
        "-pix_fmt", "yuva444p10le",
        str(output_path),
    ]
    return cmd


def render_overlay_mov(
    speeds: Iterable[float], size: Size, fps: float, output_path: Path, force: bool = False
) -> Path:
    """Render per-frame speeds to a transparent overlay ``.mov`` (Pillow → ffmpeg).

    Streams each rendered RGBA frame to ffmpeg's stdin (no temp PNGs). Raises
    PipelineError if ffmpeg exits non-zero.
    """
    cmd = build_overlay_encode_cmd(size, fps, output_path, force=force)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for speed in speeds:
            proc.stdin.write(render_frame(speed, size).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass  # ffmpeg died early; surfaced via returncode below
    proc.wait()

    if proc.returncode != 0:
        err = proc.stderr.read().decode(errors="replace").strip() if proc.stderr else ""
        raise PipelineError(
            f"ERROR: telemetry overlay encode failed (ffmpeg exit {proc.returncode}).\n{err}"
        )
    return output_path
