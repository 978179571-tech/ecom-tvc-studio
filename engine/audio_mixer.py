"""3-Layer Commercial Audio Engine (2.0):
  1. Audio-First +0% Natural TTS + WordBoundary Millisecond Cue Engine (`build_vo_timeline`)
  2. Category-Matched BGM + Emotional Low-Pass Tension -> Bright Product Reveal Curve
  3. Visual-Synced Tactile SFX (Pain Heartbeat / Stomp Impact / Optical Flash Riser / 3D Coverflow Whoosh / Loupe & Wipe SFX)
  4. Standalone Browser Live-Preview Audio Builder (`build_preview_audio_wav`)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import wave
import numpy as np

from engine.srt_sync import map_canonical_to_real

SR = 44100

CATEGORY_VOICES = {
    "medical_device": "zh-CN-YunyangNeural",
    "blue_hat": "zh-CN-YunyangNeural",
    "skincare": "zh-CN-XiaoxiaoNeural",
    "food": "zh-CN-XiaoyiNeural",
    "functional_food": "zh-CN-XiaoyiNeural",
    "general": "zh-CN-YunyangNeural",
}


def _load_stereo(path: str) -> np.ndarray:
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", path,
        "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"
    ])
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def _load_mono_with_trim(path: str, tempo: float = 1.0) -> tuple[np.ndarray, float]:
    af = f"atempo={tempo:.3f}" if tempo > 1.005 else "anull"
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", path,
        "-af", af, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"
    ])
    arr = np.frombuffer(raw, dtype=np.float32).copy()
    nz = np.where(np.abs(arr) > 0.012)[0]
    if len(nz) > 0:
        i0 = max(0, int(nz[0]) - int(0.025 * SR))
        i1 = min(len(arr), int(nz[-1]) + int(0.05 * SR))
        return arr[i0:i1], i0 / SR
    return arr, 0.0


def _load_mono(path: str, tempo: float = 1.0) -> np.ndarray:
    arr, _ = _load_mono_with_trim(path, tempo=tempo)
    return arr


def _synth_category_bgm(category: str, target_dur: float, gain: float = 0.36) -> np.ndarray:
    """Procedural stereo musical bed tailored by category when no external BGM or category preset selected."""
    n = int(SR * target_dur)
    t = np.arange(n, dtype=np.float32) / SR
    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)

    cat = (category or "general").lower()
    if cat == "skincare":
        # Airy crystal ambient chords (Fmaj7 - G6 - Em7 - Am9)
        prog = [(174.61, 220.0, 261.63, 329.63), (196.0, 246.94, 293.66, 329.63),
                (164.81, 196.0, 246.94, 293.66), (220.0, 261.63, 329.63, 392.0)]
        bar_len = 3.2
    elif cat in ("food", "functional_food"):
        # Bright warm major progression (C - G - Am - F)
        prog = [(261.63, 329.63, 392.0, 523.25), (196.0, 246.94, 392.0, 493.88),
                (220.0, 261.63, 329.63, 440.0), (174.61, 261.63, 349.23, 440.0)]
        bar_len = 2.4
    else:
        # Medical / Blue-hat authoritative warm strings & pulse (Dm - Bb - F - C)
        prog = [(146.83, 220.0, 293.66, 349.23), (116.54, 174.61, 233.08, 293.66),
                (174.61, 261.63, 349.23, 440.0), (130.81, 196.0, 261.63, 392.0)]
        bar_len = 2.8

    n_bars = int(np.ceil(target_dur / bar_len))
    for b in range(n_bars):
        i0 = int(b * bar_len * SR)
        i1 = min(n, int((b + 1) * bar_len * SR))
        if i0 >= n:
            break
        lt = np.arange(i1 - i0, dtype=np.float32) / SR
        env = np.minimum(1.0, lt / 0.25) * np.exp(-lt * 0.35)
        chord = prog[b % len(prog)]
        for ci, f in enumerate(chord):
            w = np.sin(2.0 * np.pi * f * lt) * 0.22 + np.sin(2.0 * np.pi * f * 2.0 * lt) * 0.06
            pan_l = 0.65 if ci % 2 == 0 else 0.35
            left[i0:i1] += w * env * pan_l
            right[i0:i1] += w * env * (1.0 - pan_l)

    st = np.stack([left, right], axis=1)
    pk = float(np.max(np.abs(st))) + 1e-8
    return (st / pk * gain).astype(np.float32)


def _apply_emotional_bgm_curve(bed: np.ndarray, scenes: list[dict]) -> np.ndarray:
    """Darken/muffle BGM during early pain-hook scenes, then bloom into full clarity at product entrance."""
    if not scenes or len(bed) == 0:
        return bed
    reveal_t = 0.0
    for sc in scenes:
        if sc.get("type") != "hero_hook" and not sc.get("pain_fx"):
            reveal_t = float(sc.get("start", 0.0))
            break
    if reveal_t <= 0.5:
        return bed

    n_rev = min(len(bed), int(reveal_t * SR))
    # Moving-average low-pass filter for muffled tension before product reveal
    k_len = 26
    kernel = np.ones(k_len, dtype=np.float32) / k_len
    muffled_l = np.convolve(bed[:n_rev, 0], kernel, mode="same")
    muffled_r = np.convolve(bed[:n_rev, 1], kernel, mode="same")
    muffled = np.stack([muffled_l, muffled_r], axis=1) * 0.78

    out = bed.copy()
    xf = min(n_rev, int(0.45 * SR))
    out[: n_rev - xf] = muffled[: n_rev - xf]
    if xf > 0:
        ramp = np.linspace(0.0, 1.0, xf, dtype=np.float32)[:, None]
        out[n_rev - xf: n_rev] = muffled[n_rev - xf: n_rev] * (1.0 - ramp) + bed[n_rev - xf: n_rev] * ramp
    return out


def _build_seamless_bgm(bgm_path: str, target_dur: float, gain: float = 0.46, category: str = "general", bgm_mode: str = "auto") -> np.ndarray:
    target_n = int(SR * target_dur)
    if bgm_mode == "category_synth" or not os.path.exists(bgm_path):
        return _synth_category_bgm(category, target_dur, gain=gain)
    audio = _load_stereo(bgm_path)
    orig_dur = len(audio) / SR
    if orig_dur >= target_dur:
        out = audio[:target_n]
    else:
        t_cut, t_back = min(19.40, orig_dur * 0.60), min(9.75, orig_dur * 0.28)
        xf = int(0.35 * SR)
        i_cut, i_back = int(t_cut * SR), int(t_back * SR)
        p1, p2 = audio[:i_cut], audio[i_back:]
        ang = np.linspace(0.0, np.pi / 2.0, xf, dtype=np.float32)[:, None]
        out = np.vstack([p1[:-xf], p1[-xf:] * np.cos(ang) + p2[:xf] * np.sin(ang), p2[xf:]])
        while len(out) < target_n:
            out = np.vstack([out, p2[xf:]])
        out = out[:target_n]
    return out * gain


def _add_stereo(mix, sig, t_sec, gain=1.0, pan=0.0):
    i0 = int(t_sec * SR)
    if i0 < 0 or i0 >= len(mix):
        return
    if sig.ndim == 1:
        l_g = gain * (1.0 - max(0.0, pan) * 0.4)
        r_g = gain * (1.0 + min(0.0, pan) * 0.4)
        st = np.stack([sig * l_g, sig * r_g], axis=1)
    else:
        st = sig * gain
    i1 = min(len(mix), i0 + len(st))
    mix[i0:i1] += st[: i1 - i0]


def _add_real_sfx(mix, sfx_path, t_sec, gain=0.36):
    if not os.path.exists(sfx_path):
        return
    arr = _load_stereo(sfx_path)
    mono = np.abs(arr).max(axis=1)
    nz = np.where(mono > 0.015)[0]
    if len(nz) > 0:
        arr = arr[max(0, nz[0] - int(0.01 * SR)):]
    pk = float(np.max(np.abs(arr))) + 1e-8
    _add_stereo(mix, (arr / pk).astype(np.float32), t_sec, gain=gain)


def _synth_pain_thump(dur=0.28):
    t = np.arange(int(SR * dur), dtype=np.float32) / SR
    f = 44.0 + 78.0 * np.exp(-t * 28.0)
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    sub = np.sin(ph) * np.exp(-t * 14.0) * (1.0 - np.exp(-t * 350.0))
    tap = (np.sin(2.0 * np.pi * 880.0 * t) * 0.35 + np.sin(2.0 * np.pi * 1760.0 * t) * 0.18) * np.exp(-t * 32.0)
    return (sub + tap).astype(np.float32)


def _synth_pop(f0=290.0, f1=640.0, dur=0.085):
    t = np.arange(int(SR * dur), dtype=np.float32) / SR
    f = f0 + (f1 - f0) * (1.0 - np.exp(-t * 48.0))
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    env = np.sin(np.pi * (t / dur)) ** 0.75 * np.exp(-t * 18.0)
    return (np.sin(ph) * env).astype(np.float32)


def _synth_tick(freq=1350.0, dur=0.028):
    t = np.arange(int(SR * dur), dtype=np.float32) / SR
    return (np.sin(2.0 * np.pi * freq * t) * np.exp(-t * 160.0) * (1.0 - np.exp(-t * 1400.0))).astype(np.float32)


def _synth_ding(freq=1318.5, dur=0.52):
    t = np.arange(int(SR * dur), dtype=np.float32) / SR
    atk = 1.0 - np.exp(-t * 600.0)
    sig = (
        0.72 * np.sin(2.0 * np.pi * freq * t) * np.exp(-t * 7.5)
        + 0.22 * np.sin(2.0 * np.pi * freq * 2.0 * t) * np.exp(-t * 14.0)
        + 0.08 * np.sin(2.0 * np.pi * freq * 3.0 * t) * np.exp(-t * 22.0)
    ) * atk
    return sig.astype(np.float32)


def _synth_riser(dur=0.95, f_start=180.0, f_end=1100.0):
    rng = np.random.default_rng(2026)
    n = int(SR * dur)
    t = np.arange(n, dtype=np.float32) / SR
    u = t / dur
    noise = rng.normal(0.0, 1.0, n).astype(np.float32)
    smooth = np.convolve(noise, np.ones(18, dtype=np.float32) / 18.0, mode="same")
    air = smooth * (u ** 1.8) * np.exp(-(np.maximum(0, u - 0.88) * 18.0))
    f = f_start * ((f_end / f_start) ** (u ** 1.4))
    tone = np.sin(2.0 * np.pi * np.cumsum(f) / SR) * (u ** 2.0) * 0.28 * np.sin(np.pi * u)
    return (air * 0.45 + tone).astype(np.float32)


def _synth_bloom(dur=1.45):
    t = np.arange(int(SR * dur), dtype=np.float32) / SR
    atk = 1.0 - np.exp(-t * 90.0)
    sig = np.zeros_like(t)
    for f, a, d in zip([523.25, 783.99, 1174.66, 1318.51], [0.34, 0.28, 0.22, 0.18], [2.4, 3.0, 3.8, 4.4]):
        sig += a * np.sin(2.0 * np.pi * f * t) * np.exp(-t * d)
    return (sig * atk).astype(np.float32)


def _synth_laser_sweep(dur=0.55):
    t = np.arange(int(SR * dur), dtype=np.float32) / SR
    f = 980.0 * np.exp(-t * 1.8) + 420.0
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    env = np.sin(np.pi * (t / dur)) ** 0.65
    return (np.sin(ph) * env * 0.35).astype(np.float32)


def _map_clauses_to_words(vo_text: str, words: list[dict], vo_lead: float) -> list[dict]:
    """Match punctuation-split clauses to exact WordBoundary timestamps."""
    clauses = [c.strip() for c in re.split(r"[，。！？；、,\n]+", str(vo_text or "").strip()) if c.strip()]
    if not clauses:
        return []
    if not words:
        return [{"t": round(vo_lead, 2), "text": clauses[0]}]

    cues: list[dict] = []
    w_cursor = 0
    for idx, cl in enumerate(clauses):
        if idx == 0:
            cues.append({"t": round(vo_lead + float(words[0]["t"]), 2), "text": cl})
            continue
        # Find the first word whose text matches the start of clause `cl` at or after w_cursor
        clean_cl = re.sub(r"[^\w\u4e00-\u9fff]", "", cl)
        matched_t = None
        for wi in range(w_cursor, len(words)):
            wtxt = re.sub(r"[^\w\u4e00-\u9fff]", "", words[wi]["text"])
            if wtxt and clean_cl.startswith(wtxt[: min(2, len(wtxt))]):
                matched_t = float(words[wi]["t"])
                w_cursor = wi + 1
                break
        if matched_t is None:
            # Proportional fallback across remaining words
            approx_idx = min(len(words) - 1, int(round(idx * len(words) / len(clauses))))
            matched_t = float(words[approx_idx]["t"])
            w_cursor = approx_idx + 1
        cues.append({"t": round(vo_lead + matched_t, 2), "text": cl})
    return cues


async def _synthesize_vo_and_boundaries(project_dir: str, cfg: dict, voice: str, rate: str, breath_gap: float, vo_lead: float) -> dict:
    import edge_tts

    vo_dir = os.path.join(project_dir, "out", "_vo_clips")
    os.makedirs(vo_dir, exist_ok=True)
    scenes = cfg.get("scenes") or []

    cursor_t = 0.0
    vo_lines_out = []
    scene_reports = []

    for idx, sc in enumerate(scenes):
        cid = sc.get("id", f"s{idx + 1:02d}")
        vo_text = str(sc.get("vo_text", "")).strip()
        if not vo_text:
            dur_empty = max(2.5, float(sc.get("end", cursor_t + 3.5)) - float(sc.get("start", cursor_t)))
            sc["start"] = round(cursor_t, 2)
            sc["end"] = round(cursor_t + dur_empty, 2)
            cursor_t = sc["end"]
            continue

        mp3_path = os.path.join(vo_dir, f"{cid}.mp3")
        comm = edge_tts.Communicate(vo_text, voice, rate=rate, boundary="WordBoundary")
        raw_words = []
        with open(mp3_path, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    raw_words.append({
                        "offset": chunk["offset"] / 1e7,
                        "duration": chunk["duration"] / 1e7,
                        "text": chunk["text"],
                    })

        arr, trim_s = _load_mono_with_trim(mp3_path, tempo=1.0)
        trimmed_dur = len(arr) / SR
        words = [
            {"t": round(max(0.0, w["offset"] - trim_s), 3), "d": round(w["duration"], 3), "text": w["text"]}
            for w in raw_words
        ]

        cues = _map_clauses_to_words(vo_text, words, vo_lead=vo_lead)
        sc["sub_cues"] = cues

        if sc.get("sub_style") == "pain_stomp3" and len(cues) >= 3:
            sc["stomp_cues"] = [c["t"] for c in cues[:3]]
        elif sc.get("sub_style") in ("pain_q", "pain_urgent") and len(words) >= 2:
            sc["kw_cue"] = round(vo_lead + float(words[-2]["t"]), 2)

        if sc.get("vp_mode") in ("coverflow3", "split3") and len(cues) >= 3:
            fc = [0.0] + [round(max(0.2, c["t"] - 0.05), 2) for c in cues[1:4]]
            while len(fc) < 4:
                fc.append(round(trimmed_dur * 0.85, 2))
            sc["focus_cues"] = fc[:4]

        tail_gap = breath_gap + (0.12 if idx == len(scenes) - 1 else 0.0)
        scene_dur = round(vo_lead + trimmed_dur + tail_gap, 2)
        sc["start"] = round(cursor_t, 2)
        sc["end"] = round(cursor_t + scene_dur, 2)
        sc["rec_gen_sec"] = 5 if scene_dur <= 4.8 else 10

        vo_lines_out.append({
            "id": cid,
            "start": round(sc["start"] + vo_lead, 2),
            "max_dur": round(trimmed_dur + 0.35, 2),
            "text": vo_text,
        })
        scene_reports.append({
            "id": cid,
            "start": sc["start"],
            "end": sc["end"],
            "vo_dur": round(trimmed_dur, 2),
            "rec_gen_sec": sc["rec_gen_sec"],
            "sub_cues": cues,
        })
        cursor_t = sc["end"]

    cfg["duration"] = round(cursor_t, 2)
    cfg.setdefault("audio", {})
    cfg["audio"]["enable_vo"] = True
    cfg["audio"]["voice"] = voice
    cfg["audio"]["voice_rate"] = rate
    cfg["audio"]["use_cached_vo"] = True
    cfg["audio"]["no_atempo"] = True
    cfg["audio"]["vo_lines"] = vo_lines_out

    return {
        "duration": cfg["duration"],
        "voice": voice,
        "voice_rate": rate,
        "scenes": scene_reports,
    }


def build_vo_timeline(project_dir: str, cfg: dict, voice_override: str = "", rate: str = "+0%", breath_gap: float = 0.42, vo_lead: float = 0.16) -> dict:
    """Audio-First engine: generate +0% natural VO, extract WordBoundary cues, and set exact scene timings."""
    cat = str(cfg.get("category") or "general").lower()
    voice = voice_override or cfg.get("audio", {}).get("voice") or CATEGORY_VOICES.get(cat, "zh-CN-YunyangNeural")
    return asyncio.run(_synthesize_vo_and_boundaries(project_dir, cfg, voice=voice, rate=rate, breath_gap=breath_gap, vo_lead=vo_lead))


async def _build_vo_track(project_dir: str, audio_cfg: dict, target_n: int, category: str = "general"):
    import edge_tts

    vo_dir = os.path.join(project_dir, "out", "_vo_clips")
    os.makedirs(vo_dir, exist_ok=True)
    voice = audio_cfg.get("voice") or CATEGORY_VOICES.get(category, "zh-CN-YunyangNeural")
    lines = audio_cfg.get("vo_lines", [])

    vo_track = np.zeros(target_n, dtype=np.float32)
    duck_mask = np.zeros(target_n, dtype=np.float32)

    ext_vo = audio_cfg.get("external_vo_path", "")
    if ext_vo and os.path.exists(os.path.join(project_dir, ext_vo)):
        arr = _load_mono(os.path.join(project_dir, ext_vo), 1.0)
        rms = float(np.sqrt(np.mean(arr ** 2))) + 1e-8
        arr = np.clip(arr * (0.21 / rms), -0.92, 0.92)
        n_copy = min(target_n, len(arr))
        vo_track[:n_copy] = arr[:n_copy]
        duck_mask[:n_copy] = (np.abs(arr[:n_copy]) > 0.015).astype(np.float32)
        return vo_track, duck_mask

    for line in lines:
        cid = line["id"]
        t0 = float(line["start"])
        max_d = float(line["max_dur"])
        text = str(line["text"]).strip()
        if not text:
            continue
        mp3_path = os.path.join(vo_dir, f"{cid}.mp3")
        use_cached = bool(audio_cfg.get("use_cached_vo", False))
        if not (use_cached and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 500):
            v_rate = str(audio_cfg.get("voice_rate", "+0%"))
            comm = edge_tts.Communicate(text, voice, rate=v_rate)
            await comm.save(mp3_path)
        arr = _load_mono(mp3_path, 1.0)
        dur = len(arr) / SR
        if not audio_cfg.get("no_atempo", True) and dur > max_d:
            tempo = min(1.32, dur / max_d + 0.02)
            arr = _load_mono(mp3_path, tempo)
        rms = float(np.sqrt(np.mean(arr ** 2))) + 1e-8
        arr = arr * (0.21 / rms)
        pk = float(np.max(np.abs(arr)))
        if pk > 0.92:
            arr *= (0.92 / pk)
        i0 = int(t0 * SR)
        i1 = min(target_n, i0 + len(arr))
        if i1 > i0:
            vo_track[i0:i1] += arr[: i1 - i0]
            duck_mask[max(0, i0 - int(0.12 * SR)): min(target_n, i1 + int(0.18 * SR))] = 1.0

    return vo_track, duck_mask


def build_preview_audio_wav(project_dir: str, cfg: dict, log_cb=None) -> str:
    """Build `_mix_master.wav` standalone so Web Studio can play live audio + video preview anytime."""
    target_dur = float(cfg.get("duration", 45.0))
    target_n = int(SR * target_dur)
    audio_cfg = cfg.get("audio", {})
    category = str(cfg.get("category") or "general").lower()

    enable_bgm = bool(audio_cfg.get("enable_bgm", True))
    enable_sfx = bool(audio_cfg.get("enable_sfx", True))
    enable_vo = bool(audio_cfg.get("enable_vo", False))
    bgm_gain = float(audio_cfg.get("bgm_gain", 0.44))
    sfx_scale = float(audio_cfg.get("sfx_scale", 1.0))
    bgm_mode = str(audio_cfg.get("bgm_mode", "auto"))

    if log_cb:
        log_cb("正在混音：情绪分段底乐 + 视觉绑定音效" + (" + 原速人声闪避" if enable_vo else ""))

    bgm_path = os.path.join(project_dir, "audio", "bgm_ref.wav")
    if enable_bgm:
        bed = _build_seamless_bgm(bgm_path, target_dur, gain=bgm_gain, category=category, bgm_mode=bgm_mode)
        if cfg.get("scenes"):
            bed = _apply_emotional_bgm_curve(bed, cfg.get("scenes") or [])
    else:
        bed = np.zeros((target_n, 2), dtype=np.float32)

    if enable_sfx:
        sfx_dir = os.path.join(project_dir, "audio", "sfx")
        if cfg.get("template_mode") in ("dynamic", "ref_frame") or cfg.get("scenes"):
            scenes = cfg.get("scenes") or []
            thump = _synth_pain_thump()
            pop_lo, pop_hi = _synth_pop(280.0, 580.0), _synth_pop(340.0, 700.0)
            laser = _synth_laser_sweep()
            for idx, sc in enumerate(scenes):
                st = float(sc.get("start", 0.0))
                en = float(sc.get("end", st + 3.0))
                stype = sc.get("type", "custom_card")
                sub_style = sc.get("sub_style", "")
                trans_in = sc.get("trans_in", "")
                vp_mode = sc.get("vp_mode", "")

                if idx > 0:
                    if trans_in == "optical_flash":
                        _add_stereo(bed, _synth_riser(0.65, 220.0, 1350.0), max(0.0, st - 0.58), gain=0.46 * sfx_scale)
                        _add_stereo(bed, _synth_bloom(1.35), st, gain=0.52 * sfx_scale)
                    else:
                        _add_real_sfx(bed, os.path.join(sfx_dir, "sfx_03.wav" if idx % 2 else "sfx_06.wav"), max(0.0, st - 0.12), gain=0.38 * sfx_scale)

                if sc.get("pip_loupe"):
                    _add_stereo(bed, _synth_ding(1567.98, 0.32), st + 0.35, gain=0.36 * sfx_scale, pan=0.28)
                if vp_mode == "wipe_compare" or sc.get("wipe_compare"):
                    _add_stereo(bed, laser, st + 0.45, gain=0.42 * sfx_scale)

                if sub_style == "pain_stomp3":
                    stomp_cues = sc.get("stomp_cues") or [0.16, 1.05, 1.95]
                    pans = [-0.25, 0.0, 0.25]
                    for ci_s, dt_s in enumerate(stomp_cues[:3]):
                        pn = pans[ci_s] if ci_s < len(pans) else 0.0
                        _add_stereo(bed, thump, st + float(dt_s), gain=0.54 * sfx_scale, pan=pn)
                        _add_stereo(bed, pop_hi, st + float(dt_s), gain=0.38 * sfx_scale, pan=pn)
                elif stype == "hero_hook" or sc.get("pain_fx"):
                    _add_stereo(bed, thump, st + min(0.85, (en - st) * 0.28), gain=0.52 * sfx_scale)
                    if en - st > 2.2:
                        _add_stereo(bed, thump, st + 1.65, gain=0.38 * sfx_scale)
                elif vp_mode in ("split3", "coverflow3") or stype == "orbit_cards":
                    dur_s = en - st
                    fcues = sc.get("focus_cues") or [0.10, dur_s * 0.36, dur_s * 0.64, dur_s * 0.85]
                    _add_stereo(bed, pop_lo, st + float(fcues[0]), gain=0.46 * sfx_scale, pan=-0.30)
                    if len(fcues) > 1:
                        _add_real_sfx(bed, os.path.join(sfx_dir, "sfx_05.wav"), st + float(fcues[1]) - 0.05, gain=0.36 * sfx_scale)
                        _add_stereo(bed, pop_hi, st + float(fcues[1]), gain=0.46 * sfx_scale, pan=0.0)
                    if len(fcues) > 2:
                        _add_real_sfx(bed, os.path.join(sfx_dir, "sfx_05.wav"), st + float(fcues[2]) - 0.05, gain=0.36 * sfx_scale)
                        _add_stereo(bed, pop_lo, st + float(fcues[2]), gain=0.46 * sfx_scale, pan=0.30)
                    if len(fcues) > 3:
                        _add_stereo(bed, _synth_bloom(1.25), st + float(fcues[3]), gain=0.45 * sfx_scale)
                elif stype in ("data_hud", "split_contrast", "custom_card"):
                    _add_stereo(bed, pop_lo, st + 0.55, gain=0.45 * sfx_scale, pan=-0.2)
                    if en - st > 2.0:
                        _add_stereo(bed, pop_hi, st + 1.25, gain=0.45 * sfx_scale, pan=0.2)
                elif stype == "proof_spec":
                    _add_stereo(bed, _synth_ding(1174.66), st + 0.55, gain=0.44 * sfx_scale)
                    _add_stereo(bed, _synth_ding(1396.91), st + 1.35, gain=0.46 * sfx_scale)
                elif stype == "brand_finale":
                    _add_stereo(bed, _synth_bloom(1.55), st + 0.20, gain=0.46 * sfx_scale)
                    _add_stereo(bed, _synth_ding(1046.50, 0.45), st + 0.95, gain=0.38 * sfx_scale)
        else:
            scene_timings = cfg.get("scene_timings")
            mt = lambda ts: map_canonical_to_real(ts, scene_timings)
            for ts, fn, g in [
                (3.68, "sfx_03.wav", 0.36), (7.38, "sfx_03.wav", 0.36),
                (11.08, "sfx_03.wav", 0.44), (15.08, "sfx_01.wav", 0.34),
                (18.28, "sfx_06.wav", 0.42), (23.10, "sfx_05.wav", 0.34),
                (29.88, "sfx_06.wav", 0.48), (34.28, "sfx_05.wav", 0.38),
                (38.98, "sfx_06.wav", 0.44),
            ]:
                _add_real_sfx(bed, os.path.join(sfx_dir, fn), mt(ts), gain=g * sfx_scale)

    fi, fo = int(0.30 * SR), min(len(bed), int(1.60 * SR))
    if fi > 0 and len(bed) >= fi:
        bed[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None]
    if fo > 0 and len(bed) >= fo:
        bed[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)[:, None]

    if enable_vo:
        if (cfg.get("template_mode") in ("dynamic", "ref_frame") or cfg.get("scenes")) and not audio_cfg.get("vo_lines"):
            audio_cfg = dict(audio_cfg)
            audio_cfg["vo_lines"] = [
                {
                    "id": sc.get("id", f"s{i + 1:02d}"),
                    "start": float(sc.get("start", 0.0)) + 0.14,
                    "max_dur": max(1.0, float(sc.get("end", 3.5)) - float(sc.get("start", 0.0)) - 0.25),
                    "text": sc.get("vo_text", ""),
                }
                for i, sc in enumerate(cfg.get("scenes") or [])
                if str(sc.get("vo_text", "")).strip()
            ]
        vo_track, duck_mask = asyncio.run(_build_vo_track(project_dir, audio_cfg, target_n, category=category))
        k = np.ones(int(0.15 * SR), dtype=np.float32) / int(0.15 * SR)
        smooth_duck = np.convolve(duck_mask, k, mode="same")
        bed_gain = (0.78 - 0.38 * smooth_duck)[:, None]
        mix = bed * bed_gain + np.stack([vo_track, vo_track], axis=1) * 1.06
    else:
        mix = bed

    pk = float(np.max(np.abs(mix))) if len(mix) else 0.0
    if pk > 0.96:
        mix = mix * (0.96 / pk)

    wav_path = os.path.join(project_dir, "out", "_mix_master.wav")
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    pcm = (np.clip(mix, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    return wav_path


def build_and_mux_audio(project_dir: str, cfg: dict, video_noaudio: str, out_mp4: str, log_cb=None) -> str:
    wav_path = build_preview_audio_wav(project_dir, cfg, log_cb=log_cb)
    enable_vo = bool((cfg.get("audio") or {}).get("enable_vo", False))
    target_lufs = "-14" if enable_vo else "-15"
    subprocess.check_call([
        "ffmpeg", "-y", "-v", "error",
        "-i", video_noaudio, "-i", wav_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart",
        out_mp4,
    ])
    return out_mp4
