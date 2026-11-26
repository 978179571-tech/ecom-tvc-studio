"""Reference video analyzer for ecom-tvc-studio (2.0).

Given any reference/competitor video MP4:
  1. Probes duration, resolution, FPS, and aspect ratio via ffprobe.
  2. Detects visual shot boundaries via FFmpeg scene-change detection.
  3. Automatically detects fixed top/bottom packaging bands (three-band frame contract)
     and computes the exact middle dynamic viewport aspect ratio (e.g. 16:9 vs 4:3)
     by analyzing temporal pixel variance across sampled frames.
  4. Renders a timestamped contact-sheet grid (ref_storyboard.jpg).
  5. Optionally extracts reference audio (bgm_ref.wav).
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from typing import Any

import numpy as np
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


def _detect_layout_contract(pil_frames: list[Image.Image], meta: dict[str, Any]) -> dict[str, Any]:
    """Detect whether the reference video uses a 3-band static header/footer frame or full-bleed."""
    if len(pil_frames) < 4:
        return {"layout_mode": "fullscreen", "is_three_band_frame": False}

    arrs = [np.asarray(im.resize((270, 480)), dtype=np.float32) for im in pil_frames]
    stack = np.stack(arrs, axis=0)  # (N, H, W, 3)
    row_std = stack.std(axis=0).mean(axis=(1, 2))  # (480,)
    peak = float(np.percentile(row_std, 90)) + 1e-5
    norm_std = row_std / peak

    # Find dynamic vertical span where motion exceeds 28% of 90th-percentile activity
    dyn_rows = np.where(norm_std > 0.28)[0]
    if len(dyn_rows) < 60:
        return {"layout_mode": "fullscreen", "is_three_band_frame": False}

    top_r = int(dyn_rows[0])
    bot_r = int(dyn_rows[-1])
    top_pct = round(top_r / 480.0, 3)
    bot_pct = round((480 - bot_r) / 480.0, 3)
    vp_pct = round((bot_r - top_r) / 480.0, 3)

    if top_pct >= 0.14 and bot_pct >= 0.16 and 0.24 <= vp_pct <= 0.65:
        # Map to standard 1080x1920 9:16 canvas contract
        vp_h_raw = int(round(1920 * vp_pct))
        # Classify closest standard viewport aspect ratio (16:9 = 608px, 4:3 = 810px, 1:1 = 1080px)
        candidates = [("16:9", 608), ("4:3", 810), ("1:1", 1080)]
        best_ratio, snapped_h = min(candidates, key=lambda kv: abs(kv[1] - vp_h_raw))
        top_px = int(round(1920 * top_pct))
        bot_px = 1920 - top_px - snapped_h
        return {
            "layout_mode": "ref_frame",
            "is_three_band_frame": True,
            "detected_top_pct": top_pct,
            "detected_viewport_pct": vp_pct,
            "detected_bottom_pct": bot_pct,
            "recommended_1080x1920_contract": {
                "top_band_px": top_px,
                "viewport_px": f"1080x{snapped_h}",
                "viewport_ratio": best_ratio,
                "bottom_band_px": bot_px,
            },
        }

    return {
        "layout_mode": "fullscreen",
        "is_three_band_frame": False,
        "recommended_ratio": meta.get("ratio", "9x16"),
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
    if len(raw_cuts) <= 2:
        n_segs = max(4, min(10, int(round(duration / 4.5))))
        raw_cuts = [round(i * duration / n_segs, 2) for i in range(n_segs + 1)]
    return raw_cuts


def _build_storyboard_grid(video_path: str, duration: float, out_jpg: str, max_tiles: int = 16) -> tuple[str, dict[str, Any]]:
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

    meta_dummy = {"ratio": "9x16" if imgs[0][1].size[1] > imgs[0][1].size[0] else "16x9"}
    layout_contract = _detect_layout_contract([im for _, im in imgs], meta_dummy)

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
    return out_jpg, layout_contract


def _suggest_scene_skeleton(cuts: list[float], layout_mode: str = "dynamic") -> list[dict[str, Any]]:
    n = len(cuts) - 1
    scenes: list[dict[str, Any]] = []
    for i in range(n):
        st, en = cuts[i], cuts[i + 1]
        if i == 0:
            stype, title, sub_s, trans = "hero_hook", "痛点钩子1 · 真实场景直击", "pain_q", "none"
        elif i == 1 and n >= 6:
            stype, title, sub_s, trans = "hero_hook", "痛点钩子2 · 症状递进冲击", "pain_stomp3", "whip_zoom"
        elif i == 2 and n >= 7:
            stype, title, sub_s, trans = "hero_hook", "痛点钩子3 · 紧迫警示收束", "pain_urgent", "whip_zoom"
        elif i == n - 1:
            stype, title, sub_s, trans = "brand_finale", "修护收尾与品牌落版", "pro_glass", "dissolve"
        elif (i == 3 and n >= 7) or (i == 1 and n < 6):
            stype, title, sub_s, trans = "proof_spec", "产品高光亮相 · 官方多图参考动态展台", "pro_glass", "optical_flash"
        elif i == max(2, n // 2):
            stype, title, sub_s, trans = "data_hud", "核心3D微距机理可视化", "pro_glass", "dissolve"
        elif i == max(3, n // 2 + 1) and n >= 6:
            stype, title, sub_s, trans = "orbit_cards", "多场景适用人群 · 3D轮播聚焦", "pro_glass", "dissolve"
        else:
            stype, title, sub_s, trans = "custom_card", f"第 {i + 1} 幕卖点与实证承接", "pro_glass", "dissolve"
        scenes.append({
            "id": f"s{i + 1:02d}",
            "frame_slot": f"s{i + 1:02d}",
            "vp_mode": "coverflow3" if stype == "orbit_cards" and layout_mode == "ref_frame" else "clip",
            "type": stype,
            "trans_in": trans,
            "sub_style": sub_s,
            "start": st,
            "end": en,
            "badge": "多场景适用人群" if stype == "orbit_cards" else "",
            "title": title,
            "subtitle": "请结合产品事实库填入本幕卖点，随后运行 build-vo 用原速配音反推精确秒数",
            "highlight": "",
            "vo_text": "",
            "media": "",
            "items": [],
        })
    return scenes


def analyze_reference_video(
    video_path: str,
    out_dir: str,
    extract_audio_path: str | None = None,
) -> dict[str, Any]:
    """Analyze a reference MP4 and write storyboard grid + layout contract + JSON analysis."""
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"参考视频不存在：{video_path}")
    os.makedirs(out_dir, exist_ok=True)
    meta = _probe_video(video_path)
    cuts = _detect_cuts(video_path, meta["duration"])
    grid_path, layout_contract = _build_storyboard_grid(video_path, meta["duration"], os.path.join(out_dir, "ref_storyboard.jpg"))
    tmode = layout_contract.get("layout_mode", "dynamic")
    skeleton = _suggest_scene_skeleton(cuts, layout_mode=tmode)

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
        "layout_contract": layout_contract,
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
