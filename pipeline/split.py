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


def _by_length(silences: list[tuple[int, int]], needed: int, rate: int) -> list[tuple[int, int]]:
    """Choose line breaks as the longest pauses. Refuses when length alone cannot tell them apart."""
    ranked = sorted(silences, key=lambda s: s[1] - s[0], reverse=True)
    if needed and len(ranked) > needed:
        shortest_break = ranked[needed - 1][1] - ranked[needed - 1][0]
        longest_inner = ranked[needed][1] - ranked[needed][0]
        if shortest_break < CLEAR_MARGIN * longest_inner:
            raise SplitError(
                f"ambiguous: the shortest line break ({shortest_break / rate:.2f} s) is not clearly longer "
                f"than a pause inside a line ({longest_inner / rate:.2f} s)"
            )
    return ranked[:needed]


def _by_text(silences: list[tuple[int, int]], quiet: list[bool], size: int, weights: list[float]) -> list[tuple[int, int]]:
    """Choose line breaks as the pauses nearest to where the text says each line should end.

    A line's share of the speaking time is close to its share of the characters, so the break after
    line i should fall where that fraction of the speech has been spoken. Pauses are matched to the
    expected positions in order, minimising the total distance.
    """
    spoken_before = [0]
    for is_quiet in quiet:
        spoken_before.append(spoken_before[-1] + (0 if is_quiet else 1))
    total_spoken = spoken_before[-1] or 1
    silences = sorted(silences)
    position = [spoken_before[min(start // size, len(quiet))] / total_spoken for start, _ in silences]
    total_weight = float(sum(weights))
    expected, running = [], 0.0
    for weight in weights[:-1]:
        running += weight
        expected.append(running / total_weight)
    tolerance = 0.5 * min(weights) / total_weight

    count, needed = len(silences), len(expected)
    infinity = float("inf")
    # best[j][k]: lowest cost of placing the first j breaks using only the first k pauses.
    best = [[infinity] * (count + 1) for _ in range(needed + 1)]
    took = [[False] * (count + 1) for _ in range(needed + 1)]
    best[0] = [0.0] * (count + 1)
    for j in range(1, needed + 1):
        for k in range(j, count + 1):
            distance = abs(position[k - 1] - expected[j - 1])
            use = best[j - 1][k - 1] + distance if distance <= tolerance else infinity
            skip = best[j][k - 1]
            best[j][k], took[j][k] = (use, True) if use < skip else (skip, False)
    if best[needed][count] == infinity:
        raise SplitError("no pause is close to where the text says a line should end")
    chosen, j, k = [], needed, count
    while j:
        if took[j][k]:
            chosen.append(silences[k - 1])
            j -= 1
        k -= 1
    return chosen


def split_take(data: bytes, lines: int, weights: list[float] | None = None) -> list[bytes]:
    """Return `lines` WAV clips cut at pauses, each trimmed of dead air.

    Without weights the longest pauses are the line breaks. With weights (the length of each line's
    text) the breaks are the pauses nearest to where each line should end, which still works when
    the speaker pauses as long at a comma as between lines.
    """
    samples, rate = _read(data)
    quiet, size = _quiet_windows(samples, rate)
    silences = _interior_silences(quiet, size, rate)
    needed = lines - 1
    if weights is not None and len(weights) != lines:
        raise SplitError(f"got {len(weights)} weights for {lines} lines")
    if len(silences) < needed:
        raise SplitError(f"found {len(silences)} pauses but need {needed} to separate {lines} lines")
    if weights is None:
        chosen = _by_length(silences, needed, rate)
    else:
        chosen = _by_text(silences, quiet, size, [float(w) for w in weights]) if needed else []
    cuts = sorted((start + end) // 2 for start, end in chosen)
    edges = [0, *cuts, len(samples)]
    return [_write(_trim(samples[a:b], rate), rate) for a, b in zip(edges, edges[1:])]
