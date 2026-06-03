"""Speed smoothing and frame-rate resampling — pure functions.

No I/O, no third-party deps. These take device-speed samples (from the TCX
ingester) and produce a per-frame speed series. Garmin records at irregular
intervals, so every step here is **time-based** (keyed on seconds, never on a
sample index).

A "sample" throughout is a ``(t_seconds_from_start, speed_kmh)`` tuple.
"""

import bisect

Sample = tuple[float, float]


def smooth(samples: list[Sample], window_s: float) -> list[Sample]:
    """Time-based moving average over a +/- window_s/2 window around each sample.

    Window is in seconds (not samples), so it behaves consistently despite the
    irregular point spacing. window_s <= 0 returns the samples unchanged.
    """
    if window_s <= 0 or len(samples) < 2:
        return list(samples)
    half = window_s / 2
    times = [t for t, _ in samples]
    out: list[Sample] = []
    for t, _ in samples:
        lo = bisect.bisect_left(times, t - half)
        hi = bisect.bisect_right(times, t + half)
        window = [v for _, v in samples[lo:hi]]
        out.append((t, sum(window) / len(window)))
    return out


def resample_to_frames(samples: list[Sample], fps: float, duration_s: float) -> list[float]:
    """Linearly interpolate samples onto a frame grid → one speed (km/h) per frame.

    Produces ``round(duration_s * fps)`` values for frame times 0, 1/fps, 2/fps, …
    Frames before the first / after the last sample hold the endpoint value.
    """
    if fps <= 0 or duration_s <= 0 or not samples:
        return []
    times = [t for t, _ in samples]
    values = [v for _, v in samples]
    frames = round(duration_s * fps)
    out: list[float] = []
    for k in range(frames):
        t = k / fps
        if t <= times[0]:
            out.append(values[0])
        elif t >= times[-1]:
            out.append(values[-1])
        else:
            i = bisect.bisect_right(times, t)  # times[i-1] <= t < times[i]
            t0, t1 = times[i - 1], times[i]
            v0, v1 = values[i - 1], values[i]
            out.append(v0 + (v1 - v0) * (t - t0) / (t1 - t0))
    return out
