"""Shared data models."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Clip:
    """A single DJI source clip parsed from its filename."""

    path: Path
    counter: int          # the 4-digit XXXX sequence number
    created: datetime     # parsed from the YYYYMMDDHHMMSS stamp
    stamp: str            # raw 14-digit datetime string (for output naming)
