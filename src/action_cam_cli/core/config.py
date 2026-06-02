"""Shared configuration: constants, the ``Clip`` data model, and asset paths.

Everything the CLI and the grading pipeline both depend on lives here, so future
features (e.g. telemetry generation) can import from a single place.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# --- Asset path resolution -------------------------------------------------
# The LUT ships in the top-level ``assets/`` directory (a sibling of ``src/``),
# NOT inside the importable package. Because the tool is installed editable
# (``pip install -e .``) and may be invoked from any working directory, we resolve
# the asset relative to THIS file rather than the cwd: ascend from the package
# toward the project root until ``assets/luts/dji-action-4.cube`` is found.
#
# (``importlib.resources`` is intentionally not used: it addresses files packaged
# *inside* a module, whereas this asset deliberately sits outside the package.)
_LUT_RELPATH = Path("assets") / "luts" / "dji-action-4.cube"


def get_lut_path() -> Path:
    """Locate ``assets/luts/dji-action-4.cube`` relative to the installed package.

    Walks upward from this module's location to the project root that holds the
    top-level ``assets/`` directory, independent of the current working directory.
    Returns the canonical expected path even when the file is missing, so callers
    can surface a clear "not found" error.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _LUT_RELPATH
        if candidate.is_file():
            return candidate
    # Fall back to the canonical editable-install location:
    #   <root>/src/action_cam_cli/core/config.py  ->  parents[3] == <root>
    return here.parents[3] / _LUT_RELPATH


LUT_PATH: Path = get_lut_path()

# --- External tooling ------------------------------------------------------
REQUIRED_BINARIES: tuple[str, ...] = ("ffmpeg", "ffprobe")

# --- DJI filename convention: DJI_YYYYMMDDHHMMSS_XXXX_D.MP4 -----------------
#   group 1: 14-digit datetime stamp
#   group 2: 4-digit sequential counter
# Matched case-insensitively; only the .mp4 extension is accepted (proxies are .LRF).
DJI_NAME_RE = re.compile(r"^DJI_(\d{14})_(\d{4})_D\.mp4$", re.IGNORECASE)
DJI_DATETIME_FMT = "%Y%m%d%H%M%S"

# --- FFmpeg parameters -----------------------------------------------------
# NOTE: these values define the encoding behavior and must not be altered.
# Audio filter to tame the Action 4 mic's low-frequency boominess (low-shelf cut).
AUDIO_FILTER = "bass=g=-6:f=150"

# NVENC output flags (10-bit HEVC).
NVENC_OUTPUT_ARGS: list[str] = [
    "-c:v", "hevc_nvenc",
    "-preset", "p6",
    "-cq", "19",
    "-pix_fmt", "p010le",
    "-c:a", "aac",
    "-b:a", "320k",
]


@dataclass
class Clip:
    """A single DJI source clip parsed from its filename."""

    path: Path
    counter: int          # the 4-digit XXXX sequence number
    created: datetime     # parsed from the YYYYMMDDHHMMSS stamp
    stamp: str            # raw 14-digit datetime string (for output naming)
