"""Music stage. For now only the radio-cut placeholder: a quiet synthesised pad, not a model output."""
from __future__ import annotations

from pathlib import Path

from pipeline.common import OUTPUTS, cache_key, is_cached, mark_output, run_ffmpeg

VERSION = "1"
# F major triad, an octave apart from the voice's main energy, with a slow swell.
_PAD = (
    "0.10*(sin(2*PI*174.61*t)+0.8*sin(2*PI*220.00*t)+0.7*sin(2*PI*261.63*t)+0.35*sin(2*PI*349.23*t))"
    "*(0.65+0.35*sin(2*PI*0.08*t))"
)


def placeholder(duration: float, out_dir: Path | None = None) -> Path:
    """A placeholder bed so the radio cut is not dry. Deterministic FFmpeg synthesis, cached by length."""
    output = (out_dir or OUTPUTS / "music") / "placeholder.wav"
    seconds = round(duration + 1.0, 2)
    key = cache_key("music_placeholder", VERSION, {"seconds": seconds, "expr": _PAD})
    if is_cached(output, key):
        print("  music placeholder: cache hit")
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    fade_out = max(0.0, seconds - 3.0)
    run_ffmpeg([
        "-f", "lavfi", "-i", f"aevalsrc={_PAD}:s=48000:d={seconds}",
        "-af", f"lowpass=f=1400,aecho=0.6:0.5:120|240:0.3|0.2,afade=t=in:d=2,afade=t=out:st={fade_out}:d=3",
        "-ac", "2", "-c:a", "pcm_s16le", str(output),
    ])
    mark_output(output, key, {"kind": "placeholder", "seconds": seconds, "note": "FFmpeg synthesis, not a model"})
    print(f"  music placeholder: synthesised {seconds:.1f} s")
    return output
