"""Cross-cutting configuration and the shared stderr helper.

Only genuinely cross-cutting things live here (asset paths, external-tool names,
the ``eprint`` helper). Domain-specific constants live in their own domain modules
— e.g. the NVENC flags in ``grading/ffmpeg.py`` and the DJI filename regex in
``grading/sessions.py`` (see ADR 0002).
"""

import sys
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


def eprint(*args, **kwargs):
    """Print to stderr so stdout stays clean for machine-readable output."""
    print(*args, file=sys.stderr, **kwargs)
