"""SRT subtitle parser & 10-scene auto-alignment engine for ecom-tvc-studio.

Parses standard .srt subtitle files and maps them onto the 10 canonical
e-commerce commercial scenes (S1..S7), updating:
  - cfg["duration"]
  - cfg["scene_timings"] (piecewise-linear real <-> canonical time map)
  - cfg["audio"]["vo_lines"] (exact timestamps + zero-overlap max_dur + text)
"""

from __future__ import annotations

import re
from typing import Any

CANONICAL_SCENES: list[dict[str, Any]] = [
    {"id": "01_s1",  "label": "S1 上楼痛点",       "canon_start": 0.00,  "canon_end": 3.80},
    {"id": "02_s2a", "label": "S2A 扶腰痛点",      "canon_start": 3.80,  "canon_end": 7.45},
    {"id": "03_s2b", "label": "S2B 夜间抽筋",      "canon_start": 7.45,  "canon_end": 11.10},
    {"id": "04_s3",  "label": "S3 X光透视",        "canon_start": 11.10, "canon_end": 15.10},
    {"id": "05_s4",  "label": "S4 纯白单钙瓶",     "canon_start": 15.10, "canon_end": 18.30},
    {"id": "06_s5a", "label": "S5A 营养类比1+2",   "canon_start": 18.30, "canon_end": 23.10},
    {"id": "07_s5b", "label": "S5B 营养类比3+4",   "canon_start": 23.10, "canon_end": 28.00},
    {"id": "08_s5c", "label": "S5C 注入屈伸",      "canon_start": 28.00, "canon_end": 34.30},
    {"id": "09_s6",  "label": "S6 蓝帽+小胶囊",    "canon_start": 34.30, "canon_end": 39.00},
    {"id": "10_s7",  "label": "S7 暖阳大牌落版",   "canon_start": 39.00, "canon_end": 45.00},
]

_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def _to_sec(h: str, m: str, s: str, ms: str) -> float:
    ms_val = int(ms.ljust(3, "0")[:3])
    return int(h) * 3600 + int(m) * 60 + int(s) + ms_val / 1000.0


def parse_srt(srt_text: str) -> list[dict[str, Any]]:
    """Parse SRT text into a list of {index, start, end, text} dicts."""
    text = srt_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n+", text.strip())
    entries: list[dict[str, Any]] = []

    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        time_idx = -1
        match = None
        for i, ln in enumerate(lines[:2]):
            m = _TIME_RE.search(ln)
            if m:
                time_idx = i
                match = m
                break
        if match is None:
            continue
        start = _to_sec(*match.groups()[:4])
        end = _to_sec(*match.groups()[4:])
        if end <= start:
            end = start + 0.5
        caption = " ".join(lines[time_idx + 1 :]).strip()
        caption = re.sub(r"<[^>]+>", "", caption).strip()
        entries.append({
            "index": len(entries) + 1,
            "start": round(start, 3),
            "end": round(end, 3),
            "text": caption,
        })

    if not entries:
        raise ValueError("未解析到有效的 SRT 字幕时间轴，请检查文件格式（HH:MM:SS,mmm --> HH:MM:SS,mmm）。")
    return entries


def _group_entries_to_n(entries: list[dict[str, Any]], n_scenes: int) -> list[list[dict[str, Any]]]:
    """Partition >= n_scenes contiguous entries into n_scenes non-empty groups."""
    total = len(entries)
    if total == n_scenes:
        return [[e] for e in entries]
    groups: list[list[dict[str, Any]]] = []
    for i in range(n_scenes):
        lo = int(round(i * total / n_scenes))
        hi = int(round((i + 1) * total / n_scenes))
        if hi <= lo:
            hi = lo + 1
        groups.append(entries[lo:hi])
    return groups


def sync_srt_to_config(cfg: dict[str, Any], srt_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Align a project config's 10 scenes, duration, and VO lines to an SRT file."""
    entries = parse_srt(srt_text)
    n = len(CANONICAL_SCENES)
    last_end = max(e["end"] for e in entries)
    total_dur = round(max(last_end + 1.0, 12.0), 2)

    raw_windows: list[dict[str, Any]] = []
    if len(entries) >= n:
        groups = _group_entries_to_n(entries, n)
        for scene, grp in zip(CANONICAL_SCENES, groups):
            g_start = grp[0]["start"]
            g_end = grp[-1]["end"]
            g_text = "，".join(e["text"] for e in grp if e["text"])
            raw_windows.append({
                "id": scene["id"],
                "label": scene["label"],
                "canon_start": scene["canon_start"],
                "canon_end": scene["canon_end"],
                "vo_start": round(g_start, 2),
                "vo_end": round(g_end, 2),
                "text": g_text,
            })
    else:
        # Fewer than 10 cues: map proportionally onto canonical 45s timeline
        scale = total_dur / 45.0
        for scene in CANONICAL_SCENES:
            s0 = round(scene["canon_start"] * scale, 2)
            s1 = round(scene["canon_end"] * scale, 2)
            mid_texts = [
                e["text"] for e in entries
                if ((e["start"] + e["end"]) * 0.5) >= s0 and ((e["start"] + e["end"]) * 0.5) < s1
            ]
            raw_windows.append({
                "id": scene["id"],
                "label": scene["label"],
                "canon_start": scene["canon_start"],
                "canon_end": scene["canon_end"],
                "vo_start": s0,
                "vo_end": s1,
                "text": "，".join(t for t in mid_texts if t),
            })

    # Build gap-free contiguous scene_timings covering [0.0, total_dur]
    scene_timings: list[dict[str, Any]] = []
    boundaries: list[float] = [0.0]
    for i in range(n - 1):
        cur_end = raw_windows[i]["vo_end"]
        nxt_start = raw_windows[i + 1]["vo_start"]
        mid = round((cur_end + nxt_start) * 0.5, 2) if nxt_start >= cur_end else round(nxt_start, 2)
        # Ensure strictly increasing boundaries
        mid = max(boundaries[-1] + 0.4, min(mid, total_dur - (n - 1 - i) * 0.4))
        boundaries.append(round(mid, 2))
    boundaries.append(total_dur)

    vo_lines: list[dict[str, Any]] = []
    for i, rw in enumerate(raw_windows):
        st = boundaries[i]
        en = boundaries[i + 1]
        scene_timings.append({
            "id": rw["id"],
            "label": rw["label"],
            "start": st,
            "end": en,
            "canon_start": rw["canon_start"],
            "canon_end": rw["canon_end"],
        })
        vo_start = max(st + 0.05, rw["vo_start"])
        max_dur = round(max(0.6, en - vo_start - 0.12), 2)
        vo_lines.append({
            "id": rw["id"],
            "start": round(vo_start, 2),
            "max_dur": max_dur,
            "text": rw["text"],
        })

    cfg["duration"] = total_dur
    cfg["scene_timings"] = scene_timings
    cfg.setdefault("audio", {})
    cfg["audio"]["vo_lines"] = vo_lines
    cfg["audio"]["enable_vo"] = True

    summary = {
        "srt_entries": len(entries),
        "scenes": len(scene_timings),
        "duration": total_dur,
        "scene_timings": scene_timings,
    }
    return cfg, summary


def reset_scene_timings(cfg: dict[str, Any]) -> dict[str, Any]:
    """Remove custom SRT scene_timings and restore default 45.0s duration."""
    cfg.pop("scene_timings", None)
    cfg["duration"] = 45.0
    return cfg


def map_canonical_to_real(canon_t: float, scene_timings: list[dict[str, Any]] | None) -> float:
    """Map a canonical 45s timestamp to the real SRT-aligned timestamp."""
    if not scene_timings:
        return canon_t
    for seg in scene_timings:
        c0 = float(seg["canon_start"])
        c1 = float(seg["canon_end"])
        if canon_t <= c1 or seg is scene_timings[-1]:
            r0 = float(seg["start"])
            r1 = float(seg["end"])
            u = 0.0 if c1 <= c0 else max(0.0, min(1.0, (canon_t - c0) / (c1 - c0)))
            return r0 + u * (r1 - r0)
    return canon_t
