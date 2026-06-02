"""Execution of a single grading session.

Owns the side-effecting half of the pipeline: spawning ffmpeg, driving the progress
bar, draining stderr, and handling Ctrl-C cleanup. Kept separate from ``ffmpeg.py``
(pure command building) so the command construction can be unit-tested without
touching a subprocess.
"""

import subprocess
import sys
import threading

try:
    from tqdm import tqdm
except ImportError:  # tqdm is optional; fall back to coarse percentage logging.
    tqdm = None

from action_cam_cli.core.config import eprint
from action_cam_cli.core.probe import probe_duration
from action_cam_cli.grading.ffmpeg import build_ffmpeg_command


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


def _remove_partial(output_path):
    """Delete an incomplete output file, if present."""
    try:
        if output_path.exists():
            output_path.unlink()
            eprint(f"  Removed incomplete output: {output_path}")
    except OSError as exc:
        eprint(f"  WARNING: could not remove incomplete output {output_path}: {exc}")


def run_session(session, output_path, force: bool, label: str):
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
