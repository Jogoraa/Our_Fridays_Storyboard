"""Shots stage: one clip per shot per aspect ratio, exactly as long as the timeline says.

A shot renders as a moving still (a slow camera move over its keyframe, done in FFmpeg) unless the
storyboard asks for video and a generated clip is available, in which case that clip is conformed.
If video was asked for but no clip exists, the shot falls back to the moving still and says so.
"""
from __future__ import annotations

from pathlib import Path

from pipeline.common import OUTPUTS, cache_key, is_cached, mark_output, probe_duration, run_ffmpeg
from pipeline.timing import FPS

VERSION = "1"
ZOOM = 0.10          # how far a move travels: 10% of the frame over the whole shot
OVERSAMPLE = 2       # zoompan works on integer pixels; a larger canvas hides the stepping


def aspect_tag(aspect: str) -> str:
    return aspect.replace(":", "x")


def keyframe_path(shot_id: str, aspect: str, root: Path | None = None) -> Path:
    return (root or OUTPUTS / "keyframes") / f"{shot_id}_{aspect_tag(aspect)}.jpg"


def video_source_path(shot_id: str, aspect: str, root: Path | None = None) -> Path:
    return (root or OUTPUTS / "video") / f"{shot_id}_{aspect_tag(aspect)}.mp4"


def move_filter(move: str, frames: int, width: int, height: int) -> str:
    """FFmpeg filter for a slow camera move over a still. One gentle movement per shot."""
    big_w, big_h = width * OVERSAMPLE, height * OVERSAMPLE
    progress = f"(on/{max(1, frames - 1)})"
    centre_x, centre_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    travel_x, travel_y = "(iw-iw/zoom)", "(ih-ih/zoom)"
    fixed = 1 + ZOOM
    moves = {
        "push_in": (f"1+{ZOOM}*{progress}", centre_x, centre_y),
        "pull_out": (f"{fixed}-{ZOOM}*{progress}", centre_x, centre_y),
        "pan_right": (f"{fixed}", f"{travel_x}*{progress}", centre_y),
        "pan_left": (f"{fixed}", f"{travel_x}*(1-{progress})", centre_y),
        "tilt_down": (f"{fixed}", centre_x, f"{travel_y}*{progress}"),
        "tilt_up": (f"{fixed}", centre_x, f"{travel_y}*(1-{progress})"),
        "static": ("1", "0", "0"),
    }
    zoom, x, y = moves[move]
    return (
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase:flags=lanczos,crop={big_w}:{big_h},"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={FPS},"
        f"setsar=1,format=yuv420p"
    )


def _encode_args() -> list[str]:
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]


def render(
    sb: dict,
    timing: dict,
    aspect: str,
    *,
    keyframes: Path | None = None,
    videos: Path | None = None,
    out_dir: Path | None = None,
    only_shot: str | None = None,
    force: bool = False,
) -> dict[str, Path]:
    """Make every clip for one aspect ratio. Returns shot id -> clip path."""
    size = next(f for f in sb["formats"] if f["aspect_ratio"] == aspect)
    width, height = size["width"], size["height"]
    out_dir = out_dir or OUTPUTS / "clips"
    slots = {slot["id"]: slot for slot in timing["shots"]}
    clips: dict[str, Path] = {}

    for shot in sb["shots"]:
        shot_id = shot["id"]
        output = out_dir / f"{shot_id}_{aspect_tag(aspect)}.mp4"
        clips[shot_id] = output
        if only_shot and shot_id != only_shot:
            continue
        duration = slots[shot_id]["duration"]
        frames = round(duration * FPS)
        still = keyframe_path(shot_id, aspect, keyframes)
        video = video_source_path(shot_id, aspect, videos)
        wants_video = shot["render"][aspect] == "video"
        use_video = wants_video and video.is_file()
        if wants_video and not use_video:
            print(f"  shot {shot_id} [{aspect}]: no generated clip yet, falling back to a moving still")
        source = video if use_video else still
        if not source.is_file():
            raise FileNotFoundError(f"{shot_id} [{aspect}]: missing {source.name}; run the keyframes stage first")

        mode = "video" if use_video else "still"
        key = cache_key(
            "shots", VERSION,
            {"mode": mode, "move": shot["camera_move"], "frames": frames, "width": width, "height": height, "zoom": ZOOM},
            [source],
        )
        if not force and is_cached(output, key):
            print(f"  shot {shot_id} [{aspect}]: cache hit")
            continue

        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(output.stem + ".tmp.mp4")
        if use_video:
            # Generated clips are short: slow them slightly if needed and hold the last frame to fill the shot.
            have = probe_duration(video)
            stretch = min(1.25, max(1.0, duration / have))
            chain = (
                f"setpts={stretch}*PTS,scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={width}:{height},fps={FPS},tpad=stop_mode=clone:stop_duration={duration},setsar=1,format=yuv420p"
            )
            run_ffmpeg(["-i", str(video), "-vf", chain, "-t", f"{duration}", *_encode_args(), str(temp)])
        else:
            chain = move_filter(shot["camera_move"], frames, width, height)
            run_ffmpeg(["-loop", "1", "-i", str(still), "-vf", chain, "-frames:v", str(frames), *_encode_args(), str(temp)])
        temp.replace(output)
        mark_output(output, key, {"shot": shot_id, "aspect": aspect, "mode": mode, "seconds": duration})
        print(f"  shot {shot_id} [{aspect}]: rendered {mode}, {duration:.2f} s")
    return clips
