"""Cut one long narration take into per-shot clips at its longest pauses.

Free speech quota is counted per request, so the whole film is recorded in one request and split here.
Pure Python on 16-bit mono WAV: no model, no FFmpeg, the same input always gives the same clips.
"""
from __future__ import annotations

import array
import io
import math
import wave

WINDOW = 0.02          # seconds of audio per loudness measurement
MIN_SILENCE = 0.25     # a pause shorter than this is just speech rhythm
AIR = 0.08             # silence kept at each end of a clip so words are not clipped
CLEAR_MARGIN = 1.3     # a line break must be this much longer than the longest pause inside a line


class SplitError(Exception):
    """The take could not be cut into the expected number of lines with confidence."""


def _read(data: bytes) -> tuple[array.array, int]:
    with wave.open(io.BytesIO(data), "rb") as handle:
        if handle.getsampwidth() != 2 or handle.getnchannels() != 1:
            raise SplitError("expected 16-bit mono audio")
        return array.array("h", handle.readframes(handle.getnframes())), handle.getframerate()


def _write(samples: array.array, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def _quiet_windows(samples: array.array, rate: int) -> tuple[list[bool], int]:
    size = max(1, int(rate * WINDOW))
    levels = []
    for start in range(0, len(samples), size):
        chunk = samples[start:start + size]
        levels.append(math.sqrt(sum(s * s for s in chunk) / len(chunk)) if chunk else 0.0)
    threshold = max(60.0, 0.04 * max(levels, default=0.0))
    return [level < threshold for level in levels], size


def _runs(quiet: list[bool]) -> list[tuple[int, int]]:
    """Runs of quiet windows as (first, one-past-last) window indexes."""
    runs, start = [], None
    for index, is_quiet in enumerate(quiet):
        if is_quiet and start is None:
            start = index
        elif not is_quiet and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(quiet)))
    return runs


def _interior_silences(quiet: list[bool], size: int, rate: int) -> list[tuple[int, int]]:
    """Pauses between speech, in samples. Silence before the first word or after the last is not a pause."""
    minimum = MIN_SILENCE * rate
    return [
        (first * size, last * size)
        for first, last in _runs(quiet)
        if first > 0 and last < len(quiet) and (last - first) * size >= minimum
    ]


def find_silences(data: bytes) -> list[tuple[float, float]]:
    samples, rate = _read(data)
    quiet, size = _quiet_windows(samples, rate)
    return [(start / rate, end / rate) for start, end in _interior_silences(quiet, size, rate)]


def _trim(samples: array.array, rate: int) -> array.array:
    quiet, size = _quiet_windows(samples, rate)
    loud = [index for index, is_quiet in enumerate(quiet) if not is_quiet]
    if not loud:
        return samples
    air = int(AIR * rate)
    return samples[max(0, loud[0] * size - air):min(len(samples), (loud[-1] + 1) * size + air)]


def split_take(data: bytes, lines: int) -> list[bytes]:
    """Return `lines` WAV clips, cut at the `lines - 1` longest pauses, each trimmed of dead air."""
    samples, rate = _read(data)
    quiet, size = _quiet_windows(samples, rate)
    silences = sorted(_interior_silences(quiet, size, rate), key=lambda s: s[1] - s[0], reverse=True)
    needed = lines - 1
    if len(silences) < needed:
        raise SplitError(f"found {len(silences)} pauses but need {needed} to separate {lines} lines")
    if needed and len(silences) > needed:
        shortest_break = silences[needed - 1][1] - silences[needed - 1][0]
        longest_inner = silences[needed][1] - silences[needed][0]
        if shortest_break < CLEAR_MARGIN * longest_inner:
            raise SplitError(
                f"ambiguous: the shortest line break ({shortest_break / rate:.2f} s) is not clearly longer "
                f"than a pause inside a line ({longest_inner / rate:.2f} s)"
            )
    cuts = sorted((start + end) // 2 for start, end in silences[:needed])
    edges = [0, *cuts, len(samples)]
    return [_write(_trim(samples[a:b], rate), rate) for a, b in zip(edges, edges[1:])]
