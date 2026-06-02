"""Pure FFmpeg command construction for the grading pipeline.

No subprocess execution happens here (that's ``executor.py``) — these functions
only build strings and argument lists, which keeps them trivially unit-testable.

The encoding flags below are load-bearing and tuned; see CLAUDE.md "FFmpeg
Integrity". Do not change them without an ADR.
"""

from pathlib import Path

from action_cam_cli.core.config import LUT_PATH

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


def _escape_filter_path(path: Path):
    """Escape a path for use inside an ffmpeg filtergraph option value.

    ffmpeg's filtergraph parser treats ``:`` as an option separator and ``\\`` as
    an escape character, so a native Windows path like ``C:\\luts\\x.cube`` breaks
    parsing. The portable, ffmpeg-recommended form uses forward slashes and an
    escaped drive-letter colon::

        C:\\luts\\dji-action-4.cube  ->  C\\:/luts/dji-action-4.cube

    On POSIX this is effectively a no-op for typical paths (no backslashes, no
    colon to escape).
    """
    s = str(path).replace("\\", "/")  # ffmpeg accepts '/' on every platform
    s = s.replace(":", "\\:")          # escape the drive-letter (or any) colon
    s = s.replace("'", "\\'")          # escape single quotes if present in the path
    return s


def build_filter_graph(n_clips: int, lut_path: Path):
    """Build the complex filter graph for an N-clip session.

    Concatenates video+audio across all inputs, applies the 3D LUT to the merged
    video, and applies the low-shelf bass cut to the merged audio. Outputs the
    [vout] and [aout] labels for mapping.
    """
    inputs = "".join(f"[{i}:v][{i}:a]" for i in range(n_clips))
    concat = f"{inputs}concat=n={n_clips}:v=1:a=1[vc][ac]"
    # Single quotes are required so ffmpeg's graph-level tokenizer copies the path
    # literally and preserves the backslash in '\:'; that escape is then resolved at
    # the option-parsing pass. Without the quotes the backslash is consumed too early
    # and the drive-letter colon splits the value ("No option name near '/...'").
    video = f"[vc]lut3d=file='{_escape_filter_path(lut_path)}'[vout]"
    audio = f"[ac]{AUDIO_FILTER}[aout]"
    return ";".join([concat, video, audio])


def build_ffmpeg_command(session, output_path: Path, lut_path: Path = LUT_PATH, force: bool = False):
    """Construct the full ffmpeg command (as a list of strings) for a session.

    Includes machine-readable progress on stdout (`-progress pipe:1`) and quiet
    logging so the console isn't flooded; ffmpeg's own errors still go to stderr.
    """
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-progress", "pipe:1"]
    if force:
        cmd.append("-y")
    for clip in session:
        cmd += ["-i", str(clip.path)]
    cmd += ["-filter_complex", build_filter_graph(len(session), lut_path)]
    cmd += ["-map", "[vout]", "-map", "[aout]"]
    cmd += NVENC_OUTPUT_ARGS
    cmd += [str(output_path)]
    return cmd
