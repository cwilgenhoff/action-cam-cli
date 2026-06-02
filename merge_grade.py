#!/usr/bin/env python3
"""DJI Action 4 Merge & Grade Pipeline.

Ingests chunked DJI Action 4 HEVC (D-Log M) recordings from a directory,
sorts them chronologically, concatenates them, applies a Rec.709 3D LUT, and
renders a single hardware-accelerated (NVENC) master file.

This file is built up in phases (see PRD.md). Phase 1 implemented:
  - argparse CLI (input dir, optional output dir)
  - ffmpeg / ffprobe dependency checks
  - LUT existence validation
"""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:  # tqdm is optional; fall back to coarse percentage logging.
    tqdm = None

# LUT lives in luts/ next to this script, per the PRD asset-management rule.
SCRIPT_DIR = Path(__file__).resolve().parent
LUT_PATH = SCRIPT_DIR / "luts" / "dji-action-4.cube"

# Required external binaries.
REQUIRED_BINARIES = ("ffmpeg", "ffprobe")

# DJI Action 4 naming convention: DJI_YYYYMMDDHHMMSS_XXXX_D.MP4
#   group 1: 14-digit datetime stamp
#   group 2: 4-digit sequential counter
# Matched case-insensitively; only the .mp4 extension is accepted (proxies are .LRF).
DJI_NAME_RE = re.compile(r"^DJI_(\d{14})_(\d{4})_D\.mp4$", re.IGNORECASE)
DJI_DATETIME_FMT = "%Y%m%d%H%M%S"

# Audio filter to tame the Action 4 mic's low-frequency boominess (low-shelf cut).
AUDIO_FILTER = "bass=g=-6:f=150"

# NVENC output flags (10-bit HEVC). See PRD §4 / Phase 4.
NVENC_OUTPUT_ARGS = [
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


def eprint(*args, **kwargs):
    """Print to stderr so stdout stays clean for any future machine-readable output."""
    print(*args, file=sys.stderr, **kwargs)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="merge_grade",
        description=(
            "Merge chronologically-chaptered DJI Action 4 D-Log M clips and apply "
            "a Rec.709 3D LUT, rendering a single NVENC-encoded master file."
        ),
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing the raw DJI .mp4 / .MP4 files.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write the merged master file (defaults to the input directory).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output files (passes -y to ffmpeg). Without this, "
        "sessions whose output already exists are skipped.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate sessions and print the ffmpeg command(s) to stdout without "
        "running any encode.",
    )
    return parser.parse_args(argv)


def check_dependencies(binaries=REQUIRED_BINARIES):
    """Ensure all required external binaries are on PATH.

    Returns the list of missing binaries (empty if all present).
    """
    missing = [b for b in binaries if shutil.which(b) is None]
    return missing


def validate_environment(input_dir: Path, output_dir: Path | None):
    """Validate dependencies, the LUT, and the input/output directories.

    Raises SystemExit (via sys.exit) with a non-zero code on any fatal problem,
    after logging a clear error. Returns the resolved output directory on success.
    """
    # 1. External binaries.
    missing = check_dependencies()
    if missing:
        eprint(f"ERROR: Required binaries not found on PATH: {', '.join(missing)}")
        eprint("       Install FFmpeg (which provides both ffmpeg and ffprobe) and retry.")
        sys.exit(1)

    # 2. LUT must exist before we do any expensive work.
    if not LUT_PATH.is_file():
        eprint(f"ERROR: Required LUT not found: {LUT_PATH}")
        eprint("       Place the Rec.709 conversion LUT at luts/dji-action-4.cube and retry.")
        sys.exit(1)

    # 3. Input directory must exist and be a directory.
    if not input_dir.exists():
        eprint(f"ERROR: Input directory does not exist: {input_dir}")
        sys.exit(1)
    if not input_dir.is_dir():
        eprint(f"ERROR: Input path is not a directory: {input_dir}")
        sys.exit(1)

    # 4. Resolve and prepare the output directory (defaults to input dir).
    resolved_output = output_dir if output_dir is not None else input_dir
    if resolved_output.exists() and not resolved_output.is_dir():
        eprint(f"ERROR: Output path exists but is not a directory: {resolved_output}")
        sys.exit(1)
    if not resolved_output.exists():
        try:
            resolved_output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            eprint(f"ERROR: Could not create output directory {resolved_output}: {exc}")
            sys.exit(1)

    return resolved_output


def discover_clips(input_dir: Path):
    """Scan input_dir for DJI .mp4 clips, ignoring .LRF proxies and other files.

    Returns a list of Clip objects parsed from matching filenames. Files with an
    .mp4 extension that do not match the DJI naming convention are logged and
    skipped (they cannot be grouped by sequence counter). Returns the clips
    sorted by their sequence counter.
    """
    clips = []
    skipped_unparsed = []

    for entry in sorted(input_dir.iterdir()):
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix == ".lrf":
            continue  # low-res proxy — explicitly ignored
        if suffix != ".mp4":
            continue  # not a video we handle (covers .LRF already, plus anything else)

        match = DJI_NAME_RE.match(entry.name)
        if not match:
            skipped_unparsed.append(entry.name)
            continue

        stamp, counter_str = match.group(1), match.group(2)
        try:
            created = datetime.strptime(stamp, DJI_DATETIME_FMT)
        except ValueError:
            skipped_unparsed.append(entry.name)
            continue

        clips.append(
            Clip(path=entry, counter=int(counter_str), created=created, stamp=stamp)
        )

    if skipped_unparsed:
        eprint(
            f"WARNING: {len(skipped_unparsed)} .mp4 file(s) did not match the DJI "
            f"naming convention and were skipped:"
        )
        for name in skipped_unparsed:
            eprint(f"           {name}")

    # Sort strictly by sequence counter so grouping can walk consecutive runs.
    clips.sort(key=lambda c: c.counter)
    return clips


def group_into_sessions(clips):
    """Group counter-sorted clips into recording sessions.

    Clips with perfectly consecutive sequence counters (e.g. 0012, 0013, 0014)
    belong to the same continuous recording and are merged into one session. Any
    break in the sequence starts a new session. Assumes `clips` is already sorted
    by counter (as returned by discover_clips).
    """
    sessions = []
    current = []

    for clip in clips:
        if current and clip.counter == current[-1].counter + 1:
            current.append(clip)
        else:
            if current:
                sessions.append(current)
            current = [clip]
    if current:
        sessions.append(current)

    return sessions


def output_name_for_session(session):
    """Derive the planned output filename for a session from its earliest clip."""
    earliest = min(session, key=lambda c: c.counter)
    return f"{earliest.stamp}_merged_graded.mp4"


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


def probe_video_params(path: Path):
    """Return (width, height, r_frame_rate) for a clip's first video stream.

    Raises RuntimeError if ffprobe fails or the expected fields are missing.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe failed for {path.name}: {exc.stderr.strip()}") from exc

    try:
        streams = json.loads(result.stdout).get("streams", [])
        stream = streams[0]
        return (stream["width"], stream["height"], stream["r_frame_rate"])
    except (json.JSONDecodeError, IndexError, KeyError) as exc:
        raise RuntimeError(f"Could not read video params from {path.name}") from exc


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


def probe_duration(path: Path):
    """Return the clip duration in seconds (float), or 0.0 if unavailable."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(json.loads(result.stdout)["format"]["duration"])
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError):
        return 0.0


class _PlainProgress:
    """Minimal tqdm stand-in used when tqdm isn't installed.

    Logs coarse percentage updates to stderr; no-op if total is unknown.
    """

    def __init__(self, total, desc):
        self.total = total
        self.desc = desc
        self.n = 0.0
        self._last_pct = -1

    def update(self, delta):
        self.n += delta
        if self.total:
            pct = int(self.n / self.total * 100)
            if pct != self._last_pct and pct % 5 == 0:
                self._last_pct = pct
                eprint(f"    {self.desc}: {pct}%")

    def close(self):
        pass


def _make_progress(total_seconds, desc):
    if tqdm is not None:
        return tqdm(
            total=round(total_seconds, 2) if total_seconds else None,
            desc=desc,
            unit="s",
            unit_scale=False,
            leave=True,
            file=sys.stderr,
            bar_format="    {desc}: {percentage:3.0f}%|{bar}| {n:.0f}/{total:.0f}s [{elapsed}<{remaining}]",
        )
    return _PlainProgress(total_seconds, desc)


def _remove_partial(output_path: Path):
    """Delete an incomplete output file, if present."""
    try:
        if output_path.exists():
            output_path.unlink()
            eprint(f"  Removed incomplete output: {output_path}")
    except OSError as exc:
        eprint(f"  WARNING: could not remove incomplete output {output_path}: {exc}")


def run_session(session, output_path: Path, force: bool, label: str):
    """Execute the ffmpeg render for one session with a live progress bar.

    Returns one of: "ok", "skipped", "failed". Propagates KeyboardInterrupt after
    terminating ffmpeg and cleaning up the partial output.
    """
    if output_path.exists() and not force:
        eprint(f"  SKIP: output already exists (use --force to overwrite): {output_path}")
        return "skipped"

    cmd = build_ffmpeg_command(session, output_path, force=force)
    total_seconds = sum(probe_duration(clip.path) for clip in session)

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    # Drain stderr on a thread so a full pipe can never deadlock the progress loop.
    stderr_chunks = []

    def _drain_stderr():
        for line in proc.stderr:
            stderr_chunks.append(line)

    drainer = threading.Thread(target=_drain_stderr, daemon=True)
    drainer.start()

    bar = _make_progress(total_seconds, label)
    last = 0.0
    try:
        for line in proc.stdout:
            key, sep, value = line.strip().partition("=")
            if not sep:
                continue
            if key in ("out_time_us", "out_time_ms"):  # both are microseconds in ffmpeg
                try:
                    current = int(value) / 1_000_000
                except ValueError:
                    continue
                if total_seconds:
                    current = min(current, total_seconds)  # never overshoot the estimate
                if current > last:
                    bar.update(current - last)
                    last = current
            elif key == "progress" and value == "end":
                if total_seconds and total_seconds > last:
                    bar.update(total_seconds - last)
                    last = total_seconds
        proc.wait()
    except KeyboardInterrupt:
        bar.close()
        eprint("\n  Interrupted — terminating ffmpeg...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        _remove_partial(output_path)
        raise

    bar.close()
    drainer.join(timeout=1)

    if proc.returncode != 0:
        eprint(f"  ERROR: ffmpeg exited with code {proc.returncode}")
        stderr_text = "".join(stderr_chunks).rstrip()
        if stderr_text:
            eprint(stderr_text)
        _remove_partial(output_path)
        return "failed"

    eprint(f"  Done: {output_path}")
    return "ok"


def main(argv=None):
    args = parse_args(argv)
    output_dir = validate_environment(args.input_dir, args.output_dir)

    eprint("Environment OK:")
    eprint(f"  ffmpeg/ffprobe : found on PATH")
    eprint(f"  LUT            : {LUT_PATH}")
    eprint(f"  input dir      : {args.input_dir.resolve()}")
    eprint(f"  output dir     : {output_dir.resolve()}")
    clips = discover_clips(args.input_dir)
    if not clips:
        eprint("")
        eprint(f"ERROR: No DJI .mp4 clips found in {args.input_dir.resolve()}")
        sys.exit(1)

    sessions = group_into_sessions(clips)
    report_sessions(sessions, output_dir)

    eprint("")
    if args.dry_run:
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

            output_path = output_dir / output_name_for_session(session)

            if args.dry_run:
                cmd = build_ffmpeg_command(session, output_path, force=args.force)
                eprint(f"  Command for {output_path}:")
                print(shlex.join(cmd))  # machine-readable, to stdout
                printed += 1
                continue

            result = run_session(session, output_path, args.force, label)
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
    if args.dry_run:
        eprint(f"Dry run complete: {printed} command(s) printed, {skipped} session(s) "
               f"skipped (of {total}).")
        return 0
    eprint(f"Complete: {rendered} rendered, {skipped} skipped, {failed} failed "
           f"(of {total} session(s)).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
