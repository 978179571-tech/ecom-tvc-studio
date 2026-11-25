"""Reference video analyzer for ecom-tvc-studio.

Given any reference/competitor video MP4:
  1. Probes duration, resolution, FPS, and aspect ratio via ffprobe.
  2. Detects visual shot boundaries via FFmpeg scene-change detection.
  3. Renders a timestamped contact-sheet grid (ref_storyboard.jpg) so AI Agents
     and humans can visually study pacing, framing, and scene structure.
  4. Optionally extracts reference audio (bgm_ref.wav).
  5. Outputs a starter dynamic scenes[] skeleton matching the reference rhythm.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _probe_video(video_path: str) -> dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate:format=duration",
        "-of", "json", video_path,
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    w = int(stream.get("width", 1920))
    h = int(stream.get("height", 1080))
    dur = float(fmt.get("duration", 30.0))
    rate_str = str(stream.get("r_frame_rate", "24/1"))
    if "/" in rate_str:
        num, den = rate_str.split("/", 1)
        fps = round(float(num) / max(1.0, float(den)), 2)
    else:
        fps = round(float(rate_str), 2)
    ratio = "9x16" if h > w else "16x9"
    return {
        "width": w,
        "height": h,
        "duration": round(dur, 2),
        "fps": fps,
        "ratio": ratio,
    }


def _detect_cuts(video_path: str, duration: float, threshold: float = 0.28, min_gap: float = 1.5) -> list[float]:
    cmd = [
        "ffmpeg", "-v", "info", "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
    raw_cuts = [0.0]
    for m in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", proc.stderr):
        t = float(m.group(1))
        if t - raw_cuts[-1] >= min_gap and (duration - t) >= 1.2:
            raw_cuts.append(round(t, 2))
    raw_cuts.append(round(duration, 2))
    # Fallback: if reference video is one continuous shot, split into sensible 4-5s beats
    if len(raw_cuts) <= 2:
        n_segs = max(4, min(10, int(round(duration / 4.5))))
        raw_cuts = [round(i * duration / n_segs, 2) for i in range(n_segs + 1)]
    return raw_cuts


def _build_storyboard_grid(video_path: str, duration: float, out_jpg: str, max_tiles: int = 16) -> str:
    os.makedirs(os.path.dirname(out_jpg), exist_ok=True)
    n_tiles = max(6, min(max_tiles, int(round(duration / 2.5)) + 1))
    times = [round(i * max(0.1, duration - 0.3) / max(1, n_tiles - 1), 2) for i in range(n_tiles)]
    tmp_dir = os.path.join(os.path.dirname(out_jpg), "_ref_frames")
    os.makedirs(tmp_dir, exist_ok=True)

    imgs: list[tuple[float, Image.Image]] = []
    for idx, ts in enumerate(times):
        fp = os.path.join(tmp_dir, f"t_{idx:02d}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.2f}", "-i", video_path, "-vframes", "1", "-q:v", "3", fp],
            check=False,
        )
        if os.path.exists(fp):
            imgs.append((ts, Image.open(fp).convert("RGB")))

    if not imgs:
        raise RuntimeError("无法从参考视频提取关键帧，请检查视频文件是否完整。")

    cols = 4
    rows = math.ceil(len(imgs) / cols)
    sample_w, sample_h = imgs[0][1].size
    tile_w = 320 if sample_h > sample_w else 440
    tile_h = int(tile_w * sample_h / max(1, sample_w))
    pad = 12
    grid = Image.new("RGB", (cols * tile_w + (cols + 1) * pad, rows * tile_h + (rows + 1) * pad), (18, 22, 28))
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 20)
    except Exception:
        font = ImageFont.load_default()

    for i, (ts, im) in enumerate(imgs):
        r, c = divmod(i, cols)
        x = pad + c * (tile_w + pad)
        y = pad + r * (tile_h + pad)
        resized = im.resize((tile_w, tile_h), Image.LANCZOS)
        grid.paste(resized, (x, y))
        label = f"#{i + 1:02d}  {ts:.1f}s"
        draw.rectangle([x + 6, y + 6, x + 136, y + 34], fill=(0, 0, 0))
        draw.text((x + 12, y + 9), label, fill=(255, 224, 102), font=font)
        im.close()

    grid.save(out_jpg, quality=88)
    return out_jpg


def _suggest_scene_skeleton(cuts: list[float]) -> list[dict[str, Any]]:
    n = len(cuts) - 1
    scenes: list[dict[str, Any]] = []
    for i in range(n):
        st, en = cuts[i], cuts[i + 1]
        if i == 0:
            stype, title = "hero_hook", "开场黄金3秒痛点钩子"
        elif i == n - 1:
            stype, title = "brand_finale", "品牌大牌落版与行动引导"
        elif i == n - 2 and n >= 4:
            stype, title = "proof_spec", "权威背书与核心规格特写"
        elif i == 1 and n >= 5:
            stype, title = "data_hud", "痛点根源 / 机理数据解析"
        elif i == 2 and n >= 6:
            stype, title = "split_contrast", "痛点归因 / 新旧方案对比"
        elif i == max(1, n // 2):
            stype, title = "orbit_cards", "核心成分 / 核心卖点类比拆解"
        else:
            stype, title = "custom_card", f"第 {i + 1} 幕卖点承接"
        scenes.append({
            "id": f"s{i + 1:02d}",
            "type": stype,
            "start": st,
            "end": en,
            "badge": f"SCENE {i + 1:02d}",
            "title": title,
            "subtitle": "请根据参考视频节奏与产品卖点改写此幕文案",
            "highlight": "",
            "vo_text": "",
            "media": "",
            "media_slot": "",
            "items": [],
        })
    return scenes


def analyze_reference_video(
    video_path: str,
    out_dir: str,
    extract_audio_path: str | None = None,
) -> dict[str, Any]:
    """Analyze a reference MP4 and write storyboard grid + JSON analysis."""
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"参考视频不存在：{video_path}")
    os.makedirs(out_dir, exist_ok=True)
    meta = _probe_video(video_path)
    cuts = _detect_cuts(video_path, meta["duration"])
    grid_path = _build_storyboard_grid(video_path, meta["duration"], os.path.join(out_dir, "ref_storyboard.jpg"))
    skeleton = _suggest_scene_skeleton(cuts)

    audio_extracted = None
    if extract_audio_path:
        os.makedirs(os.path.dirname(extract_audio_path), exist_ok=True)
        res = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", video_path, "-vn", "-ac", "2", "-ar", "44100", extract_audio_path],
            check=False,
        )
        if res.returncode == 0 and os.path.exists(extract_audio_path):
            audio_extracted = extract_audio_path

    analysis = {
        "source_video": os.path.abspath(video_path),
        "meta": meta,
        "cuts": cuts,
        "scene_count": len(skeleton),
        "storyboard_jpg": grid_path,
        "extracted_audio": audio_extracted,
        "suggested_scenes": skeleton,
    }
    json_path = os.path.join(out_dir, "ref_analysis.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    analysis["analysis_json"] = json_path
    return analysis
