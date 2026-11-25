"""Assembly stage. FFmpeg only: the same inputs always give the same film."""
from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline import subtitles
from pipeline.common import OUTPUTS, ProviderError, cache_key, is_cached, mark_output, run_ffmpeg
from pipeline.timing import FPS

VERSION = "2"
TARGET_LUFS = -14.0
TRUE_PEAK = -1.5   # a little under the -1 dB ceiling, because AAC encoding raises peaks slightly
# Starting point suggested in the brief; tuned by ear later and logged in EXPERIMENTS.md.
DUCKING = "sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500"
MUSIC_GAIN_DB = -14.0
FADE_IN = 0.6
FADE_TO_CARD = 0.5


def aspect_tag(aspect: str) -> str:
    return aspect.replace(":", "x")


def mix_filter(timing: dict, music_index: int) -> str:
    """Place each narration clip at its start time, duck the music under the voice, sum both."""
    parts = []
    labels = []
    tempo = timing.get("tempo", 1.0)
    faster = f"atempo={tempo}," if tempo != 1.0 else ""
    for index, slot in enumerate(timing["shots"]):
        delay = round(slot["narration_start"] * 1000)
        parts.append(f"[{index}:a]aresample=48000,{faster}aformat=channel_layouts=stereo,adelay={delay}:all=1[n{index}]")
        labels.append(f"[n{index}]")
    total = timing["total"]
    parts.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,"
        f"apad=whole_dur={total},atrim=0:{total},asplit=2[voice][key]"
    )
    fade_out = max(0.0, total - 2.5)
    parts.append(
        f"[{music_index}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total},"
        f"volume={MUSIC_GAIN_DB}dB,afade=t=out:st={fade_out}:d=2.5[bed]"
    )
    parts.append(f"[bed][key]{DUCKING}[ducked]")
    parts.append("[voice][ducked]amix=inputs=2:normalize=0[mix]")
    return ";".join(parts)


def measure_loudness(path: Path) -> dict:
    """First loudnorm pass: measure, so the second pass can correct linearly."""
    stderr = run_ffmpeg(
        ["-i", str(path), "-vn", "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11:print_format=json", "-f", "null", "-"],
        capture=True,
    )
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not blocks:
        raise ProviderError("could not read loudness measurement from FFmpeg")
    return json.loads(blocks[-1])


def loudnorm_filter(measured: dict) -> str:
    return (
        f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true"
    )


def _premix(timing: dict, narration: list[Path], music: Path, output: Path) -> dict:
    """Mix voice and ducked music to a WAV and measure its loudness."""
    inputs: list[str] = []
    for clip in narration:
        inputs += ["-i", str(clip)]
    inputs += ["-i", str(music)]
    run_ffmpeg([*inputs, "-filter_complex", mix_filter(timing, len(narration)), "-map", "[mix]", "-c:a", "pcm_s24le", str(output)])
    return measure_loudness(output)


def _audio_args(measured: dict) -> list[str]:
    return ["-af", loudnorm_filter(measured), "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]


def _video_args() -> list[str]:
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def _mix_settings() -> dict:
    return {"ducking": DUCKING, "music_gain": MUSIC_GAIN_DB, "lufs": TARGET_LUFS, "true_peak": TRUE_PEAK}


def radio_cut(
    sb: dict,
    timing: dict,
    *,
    lang: str,
    music: Path,
    narration_dir: Path | None = None,
    out_dir: Path | None = None,
    force: bool = False,
) -> Path:
    """Narration over the placeholder bed on a black screen with subtitles: the story prototype."""
    narration_dir = narration_dir or OUTPUTS / "narration" / lang
    out_dir = out_dir or OUTPUTS / "film"
    work = out_dir / "work"
    output = out_dir / f"radio_cut_{lang}.mp4"
    clips = [narration_dir / f"{slot['id']}.wav" for slot in timing["shots"]]
    width, height = 1080, 1920
    ass_text = subtitles.build_ass(sb, timing, width=width, height=height)

    key = cache_key("radio_cut", VERSION, {"timing": timing, "ass": ass_text, **_mix_settings()}, [*clips, music])
    if not force and is_cached(output, key):
        print(f"  radio cut [{lang}]: cache hit")
        return output

    work.mkdir(parents=True, exist_ok=True)
    ass_name = f"radio_cut_{lang}.ass"
    (work / ass_name).write_text(ass_text, encoding="utf-8")
    premix = work / f"radio_cut_{lang}_premix.wav"
    measured = _premix(timing, clips, music, premix)
    total = timing["total"]
    temp = output.with_name(output.stem + ".tmp.mp4")
    # Run inside the work folder so the subtitles filter gets a plain file name (no Windows path escaping).
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={FPS}:d={total}",
            "-i", premix.name,
            "-vf", f"subtitles={ass_name}",
            *_audio_args(measured), *_video_args(),
            "-t", f"{total}", "-movflags", "+faststart", str(temp.resolve()),
        ],
        cwd=work,
    )
    temp.replace(output)
    mark_output(output, key, {
        "kind": "radio_cut", "lang": lang, "seconds": round(total, 3),
        "measured_input_lufs": measured["input_i"], "target_lufs": TARGET_LUFS,
    })
    print(f"  radio cut [{lang}]: wrote {output.name} ({total:.1f} s)")
    return output


def film(
    sb: dict,
    timing: dict,
    *,
    lang: str,
    aspect: str,
    music: Path,
    clips: dict[str, Path],
    narration_dir: Path | None = None,
    out_dir: Path | None = None,
    name: str = "film",
    force: bool = False,
) -> Path:
    """The film in one aspect ratio: shots, end card, burned-in subtitles and messages, mixed sound."""
    size = next(f for f in sb["formats"] if f["aspect_ratio"] == aspect)
    width, height = size["width"], size["height"]
    narration_dir = narration_dir or OUTPUTS / "narration" / lang
    out_dir = out_dir or OUTPUTS / "film"
    work = out_dir / "work"
    tag = aspect_tag(aspect)
    output = out_dir / f"{name}_{tag}.mp4"
    narration = [narration_dir / f"{slot['id']}.wav" for slot in timing["shots"]]
    pictures = [clips[slot["id"]] for slot in timing["shots"]]
    ass_text = subtitles.build_ass(sb, timing, width=width, height=height, extras=True)

    key = cache_key(
        "film", VERSION,
        {"timing": timing, "ass": ass_text, "aspect": aspect, "fade_in": FADE_IN, "fade_to_card": FADE_TO_CARD, **_mix_settings()},
        [*pictures, *narration, music],
    )
    if not force and is_cached(output, key):
        print(f"  film [{aspect}]: cache hit")
        return output

    work.mkdir(parents=True, exist_ok=True)
    ass_name = f"{name}_{tag}.ass"
    (work / ass_name).write_text(ass_text, encoding="utf-8")
    premix = work / f"{name}_{tag}_premix.wav"
    measured = _premix(timing, narration, music, premix)

    card = timing["end_card"]
    total = timing["total"]
    inputs: list[str] = []
    for picture in pictures:
        inputs += ["-i", str(picture.resolve())]
    inputs += ["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={FPS}:d={card['duration']}"]
    inputs += ["-i", premix.name]
    count = len(pictures) + 1
    chain = (
        "".join(f"[{i}:v]" for i in range(count))
        + f"concat=n={count}:v=1:a=0,fade=t=in:st=0:d={FADE_IN},"
        + f"fade=t=out:st={card['start'] - FADE_TO_CARD}:d={FADE_TO_CARD},subtitles={ass_name}[v]"
    )
    temp = output.with_name(output.stem + ".tmp.mp4")
    run_ffmpeg(
        [
            *inputs, "-filter_complex", chain, "-map", "[v]", "-map", f"{count}:a",
            *_audio_args(measured), *_video_args(),
            "-t", f"{total}", "-movflags", "+faststart", str(temp.resolve()),
        ],
        cwd=work,
    )
    temp.replace(output)
    mark_output(output, key, {
        "kind": "film", "lang": lang, "aspect": aspect, "seconds": round(total, 3),
        "measured_input_lufs": measured["input_i"], "target_lufs": TARGET_LUFS,
    })
    print(f"  film [{aspect}]: wrote {output.name} ({total:.1f} s)")
    return output
