"""Turn measured narration lengths into the film's timeline. Picture is cut to the voice."""
from __future__ import annotations

import math

FPS = 24
MIN_SECONDS = 60.0
MAX_SECONDS = 90.0


class TimingError(Exception):
    """The measured narration does not fit the film."""


def build_timing(sb: dict, durations: dict[str, float], *, lead: float = 0.4, tail: float = 0.7) -> dict:
    """Each shot lasts lead + narration + tail, rounded up to a whole frame. Shots are contiguous."""
    shots = []
    cursor_frames = 0
    for shot in sb["shots"]:
        shot_id = shot["id"]
        if shot_id not in durations:
            raise TimingError(f"no measured narration for {shot_id}; run the narration stage first")
        narration = float(durations[shot_id])
        frames = math.ceil(round((lead + narration + tail) * FPS, 6))
        start = cursor_frames / FPS
        shots.append({
            "id": shot_id,
            "start": start,
            "duration": frames / FPS,
            "narration_start": start + lead,
            "narration_duration": narration,
        })
        cursor_frames += frames
    end_start = cursor_frames / FPS
    end_duration = float(sb["end_card"]["duration_seconds"])
    return {
        "fps": FPS,
        "shots": shots,
        "end_card": {"start": end_start, "duration": end_duration},
        "total": end_start + end_duration,
    }


def check_total(timing: dict, lo: float = MIN_SECONDS, hi: float = MAX_SECONDS) -> None:
    """Stop before assembly if the film would be outside 60-90 s, and say which shots are long."""
    total = timing["total"]
    if lo <= total <= hi:
        return
    if total > hi:
        problem = f"{total - hi:.1f} s over the {hi:g} s limit"
    else:
        problem = f"{lo - total:.1f} s under the {lo:g} s minimum"
    lines = [f"  {s['id']}: {s['duration']:.2f} s (narration {s['narration_duration']:.2f} s)" for s in timing["shots"]]
    lines.append(f"  end card: {timing['end_card']['duration']:.2f} s")
    raise TimingError(f"film would run {total:.1f} s, {problem}:\n" + "\n".join(lines))
