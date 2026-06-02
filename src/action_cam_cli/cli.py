"""Command-line interface: argument parsing and routing only.

The ``action-cam`` console script (see pyproject.toml) points at :func:`main`,
which parses arguments and delegates all work to
:func:`action_cam_cli.grading.merge_grade.run`.
"""

import argparse
import sys
from pathlib import Path

from action_cam_cli.grading.merge_grade import run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="action-cam",
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(
        args.input_dir,
        args.output_dir,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
