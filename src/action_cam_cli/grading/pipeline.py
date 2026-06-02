"""Grading pipeline orchestrator.

Wires the grading domain together: validate the environment, discover and group
clips into sessions, then render (or, for a dry run, print) each session.

Per ADR 0002, this layer raises ``PipelineError`` for fatal conditions instead of
calling ``sys.exit()`` — the CLI translates exceptions into exit codes.
"""

import shlex
import shutil
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:  # tqdm is optional; fall back to coarse percentage logging.
    tqdm = None

from action_cam_cli.core.config import LUT_PATH, REQUIRED_BINARIES, eprint
from action_cam_cli.core.errors import PipelineError
from action_cam_cli.core.probe import has_nvenc_encoder, probe_video_params
from action_cam_cli.grading.executor import run_session
from action_cam_cli.grading.ffmpeg import build_ffmpeg_command
from action_cam_cli.grading.sessions import (
    discover_clips,
    group_into_sessions,
    output_name_for_session,
)


def check_dependencies(binaries=REQUIRED_BINARIES):
    """Ensure all required external binaries are on PATH.

    Returns the list of missing binaries (empty if all present).
    """
    missing = [b for b in binaries if shutil.which(b) is None]
    return missing


def validate_environment(input_dir: Path, output_dir: Path | None, *, check_encoder: bool = False):
    """Validate dependencies, the LUT, and the input/output directories.

    When ``check_encoder`` is True, also verify that the NVENC hardware encoder is
    usable (a real render needs it; a ``--dry-run`` does not). Raises PipelineError
    with a user-facing message on any fatal problem. Returns the resolved output
    directory on success.
    """
    # 1. External binaries.
    missing = check_dependencies()
    if missing:
        raise PipelineError(
            f"ERROR: Required binaries not found on PATH: {', '.join(missing)}\n"
            "       Install FFmpeg (which provides both ffmpeg and ffprobe) and retry."
        )

    # 2. LUT must exist before we do any expensive work.
    if not LUT_PATH.is_file():
        raise PipelineError(
            f"ERROR: Required LUT not found: {LUT_PATH}\n"
            "       Place the Rec.709 conversion LUT at assets/luts/dji-action-4.cube and retry."
        )

    # 3. Input directory must exist and be a directory.
    if not input_dir.exists():
        raise PipelineError(f"ERROR: Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise PipelineError(f"ERROR: Input path is not a directory: {input_dir}")

    # 4. Resolve and prepare the output directory (defaults to input dir).
    resolved_output = output_dir if output_dir is not None else input_dir
    if resolved_output.exists() and not resolved_output.is_dir():
        raise PipelineError(f"ERROR: Output path exists but is not a directory: {resolved_output}")
    if not resolved_output.exists():
        try:
            resolved_output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PipelineError(f"ERROR: Could not create output directory {resolved_output}: {exc}")

    # 5. Hardware encoder (only required for an actual render — not a dry run).
    if check_encoder and not has_nvenc_encoder():
        raise PipelineError(
            "ERROR: NVIDIA NVENC encoder (hevc_nvenc) is not available.\n"
            "       This tool requires an NVIDIA GPU with NVENC support. Verify with:\n"
            "         ffmpeg -hide_banner -encoders | grep nvenc\n"
            "       (Use --dry-run to inspect the planned commands without a GPU.)"
        )

    return resolved_output


def validate_session_uniform(session):
    """Probe every clip in a session and ensure identical resolution + framerate.

    Returns (params, None) where params is (width, height, r_frame_rate) if the
    session is uniform, or (None, error_message) describing the first mismatch or
    probe failure.
    """
    reference = None
    for clip in session:
        try:
            params = probe_video_params(clip.path)
        except RuntimeError as exc:
            return None, str(exc)

        if reference is None:
            reference = params
        elif params != reference:
            ref_w, ref_h, ref_fps = reference
            cur_w, cur_h, cur_fps = params
            return None, (
                f"clip {clip.path.name} is {cur_w}x{cur_h}@{cur_fps}, expected "
                f"{ref_w}x{ref_h}@{ref_fps} (matching the session's first clip)"
            )
    return reference, None


def report_sessions(sessions, output_dir: Path):
    """Print the planned rendering sessions to stderr for user review."""
    total_clips = sum(len(s) for s in sessions)
    eprint("")
    eprint(f"Discovered {total_clips} DJI clip(s) across {len(sessions)} session(s):")
    for i, session in enumerate(sessions, start=1):
        first, last = session[0], session[-1]
        span = (
            f"{first.counter:04d}"
            if len(session) == 1
            else f"{first.counter:04d}–{last.counter:04d}"
        )
        out_name = output_name_for_session(session)
        eprint("")
        eprint(
            f"  Session {i}: {len(session)} clip(s)  [counters {span}]  "
            f"-> {output_dir / out_name}"
        )
        for clip in session:
            eprint(
                f"      {clip.counter:04d}  {clip.created:%Y-%m-%d %H:%M:%S}  {clip.path.name}"
            )


def run(input_dir: Path, output_dir: Path | None = None, *, force: bool = False, dry_run: bool = False) -> int:
    """Run the full merge & grade pipeline. Returns a process exit code.

    Raises PipelineError for fatal conditions; the CLI is responsible for catching
    it and translating to an exit code.
    """
    out_dir = validate_environment(input_dir, output_dir, check_encoder=not dry_run)

    eprint("Environment OK:")
    eprint(f"  ffmpeg/ffprobe : found on PATH")
    eprint(f"  LUT            : {LUT_PATH}")
    eprint(f"  input dir      : {input_dir.resolve()}")
    eprint(f"  output dir     : {out_dir.resolve()}")
    clips = discover_clips(input_dir)
    if not clips:
        raise PipelineError(f"\nERROR: No DJI .mp4 clips found in {input_dir.resolve()}")

    sessions = group_into_sessions(clips)
    report_sessions(sessions, out_dir)

    eprint("")
    if dry_run:
        eprint("DRY RUN: validating sessions and printing ffmpeg commands (no encode).")
    elif tqdm is None:
        eprint("NOTE: tqdm not installed — using plain percentage progress. "
               "Install it (pip install tqdm) for a nicer progress bar.")

    rendered = failed = skipped = printed = 0
    total = len(sessions)
    try:
        for i, session in enumerate(sessions, start=1):
            label = f"Session {i}/{total}"
            eprint("")
            eprint(f"--- {label} ---")

            params, error = validate_session_uniform(session)
            if error is not None:
                eprint(f"  SKIP: {error}")
                skipped += 1
                continue

            width, height, fps = params
            eprint(f"  Uniform: {width}x{height} @ {fps}")

            output_path = out_dir / output_name_for_session(session)

            if dry_run:
                cmd = build_ffmpeg_command(session, output_path, force=force)
                eprint(f"  Command for {output_path}:")
                print(shlex.join(cmd))  # machine-readable, to stdout
                printed += 1
                continue

            result = run_session(session, output_path, force, label)
            if result == "ok":
                rendered += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1
    except KeyboardInterrupt:
        eprint("")
        eprint("Aborted by user. Stopping remaining sessions.")
        return 130

    eprint("")
    if dry_run:
        eprint(f"Dry run complete: {printed} command(s) printed, {skipped} session(s) "
               f"skipped (of {total}).")
        return 0
    eprint(f"Complete: {rendered} rendered, {skipped} skipped, {failed} failed "
           f"(of {total} session(s)).")
    return 1 if failed else 0
