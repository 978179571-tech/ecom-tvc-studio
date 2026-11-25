"""3-Layer Commercial Audio Engine: Beat-locked BGM + 5-Layer Tactile SFX + edge-tts VO with Auto-Ducking."""

import os
import wave
import asyncio
import subprocess
import numpy as np

from engine.srt_sync import map_canonical_to_real

SR = 44100


def _load_stereo(path: str) -> np.ndarray:
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", path,
        "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"
    ])
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def _load_mono(path: str, tempo: float = 1.0) -> np.ndarray:
    af = f"atempo={tempo:.3f}" if tempo > 1.005 else "anull"
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", path,
        "-af", af, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"
    ])
    arr = np.frombuffer(raw, dtype=np.float32).copy()
    nz = np.where(np.abs(arr) > 0.012)[0]
    if len(nz) > 0:
        arr = arr[max(0, nz[0] - int(0.025 * SR)): min(len(arr), nz[-1] + int(0.05 * SR))]
    return arr


def _build_seamless_bgm(bgm_path: str, target_dur: float, gain: float = 0.46) -> np.ndarray:
    target_n = int(SR * target_dur)
    if not os.path.exists(bgm_path):
        return np.zeros((target_n, 2), dtype=np.float32)
    audio = _load_stereo(bgm_path)
    orig_dur = len(audio) / SR
    if orig_dur >= target_dur:
        out = audio[:target_n]
    else:
        # Beat-locked crossfade extension
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


async def _build_vo_track(project_dir: str, audio_cfg: dict, target_n: int):
    import edge_tts

    vo_dir = os.path.join(project_dir, "out", "_vo_clips")
    os.makedirs(vo_dir, exist_ok=True)
    voice = audio_cfg.get("voice", "zh-CN-YunyangNeural")
    lines = audio_cfg.get("vo_lines", [])

    vo_track = np.zeros(target_n, dtype=np.float32)
    duck_mask = np.zeros(target_n, dtype=np.float32)

    for line in lines:
        cid = line["id"]
        t0 = float(line["start"])
        max_d = float(line["max_dur"])
        text = str(line["text"]).strip()
        if not text:
            continue
        mp3_path = os.path.join(vo_dir, f"{cid}.mp3")
        comm = edge_tts.Communicate(text, voice, rate="+10%")
        await comm.save(mp3_path)
        arr = _load_mono(mp3_path, 1.0)
        dur = len(arr) / SR
        if dur > max_d:
            tempo = min(1.24, dur / max_d + 0.02)
            arr = _load_mono(mp3_path, tempo)
        rms = float(np.sqrt(np.mean(arr ** 2))) + 1e-8
        arr = arr * (0.21 / rms)
        pk = float(np.max(np.abs(arr)))
        if pk > 0.92:
            arr *= (0.92 / pk)
        i0 = int(t0 * SR)
        i1 = min(target_n, i0 + len(arr))
        vo_track[i0:i1] += arr[: i1 - i0]
        duck_mask[max(0, i0 - int(0.12 * SR)): min(target_n, i1 + int(0.18 * SR))] = 1.0

    return vo_track, duck_mask


def build_and_mux_audio(project_dir: str, cfg: dict, video_noaudio: str, out_mp4: str, log_cb=None):
    target_dur = float(cfg.get("duration", 45.0))
    target_n = int(SR * target_dur)
    audio_cfg = cfg.get("audio", {})

    enable_bgm = bool(audio_cfg.get("enable_bgm", True))
    enable_sfx = bool(audio_cfg.get("enable_sfx", True))
    enable_vo = bool(audio_cfg.get("enable_vo", False))
    bgm_gain = float(audio_cfg.get("bgm_gain", 0.46))
    sfx_scale = float(audio_cfg.get("sfx_scale", 1.0))

    if log_cb:
        log_cb("正在混音：底乐 + 五层音效" + (" + 人声配音闪避" if enable_vo else ""))

    bgm_path = os.path.join(project_dir, "audio", "bgm_ref.wav")
    bed = _build_seamless_bgm(bgm_path, target_dur, gain=bgm_gain) if enable_bgm else np.zeros((target_n, 2), dtype=np.float32)

    if enable_sfx:
        sfx_dir = os.path.join(project_dir, "audio", "sfx")
        if cfg.get("template_mode") == "dynamic" or cfg.get("scenes"):
            scenes = cfg.get("scenes") or []
            thump = _synth_pain_thump()
            pop_lo, pop_hi = _synth_pop(280.0, 580.0), _synth_pop(340.0, 700.0)
            for idx, sc in enumerate(scenes):
                st = float(sc.get("start", 0.0))
                en = float(sc.get("end", st + 3.0))
                stype = sc.get("type", "custom_card")
                if idx > 0:
                    _add_real_sfx(bed, os.path.join(sfx_dir, "sfx_03.wav" if idx % 2 else "sfx_06.wav"), max(0.0, st - 0.12), gain=0.38 * sfx_scale)
                if stype == "hero_hook":
                    _add_stereo(bed, thump, st + min(1.2, (en - st) * 0.35), gain=0.52 * sfx_scale)
                elif stype in ("data_hud", "split_contrast", "custom_card"):
                    _add_stereo(bed, pop_lo, st + 0.55, gain=0.45 * sfx_scale, pan=-0.2)
                    if en - st > 2.0:
                        _add_stereo(bed, pop_hi, st + 1.25, gain=0.45 * sfx_scale, pan=0.2)
                elif stype == "orbit_cards":
                    _add_stereo(bed, pop_lo, st + 0.50, gain=0.44 * sfx_scale, pan=-0.25)
                    _add_stereo(bed, pop_hi, st + 1.35, gain=0.44 * sfx_scale, pan=0.25)
                    if en - st > 3.5:
                        _add_stereo(bed, _synth_bloom(1.35), max(st + 1.8, en - 1.6), gain=0.46 * sfx_scale)
                elif stype == "proof_spec":
                    _add_stereo(bed, _synth_ding(1174.66), st + 0.65, gain=0.44 * sfx_scale)
                    _add_stereo(bed, _synth_ding(1396.91), st + 1.25, gain=0.46 * sfx_scale)
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

            thump = _synth_pain_thump()
            for ts in (1.65, 5.20, 8.70):
                _add_stereo(bed, thump, mt(ts), gain=0.58 * sfx_scale)
            tick = _synth_tick()
            for ts in (4.62, 4.86, 5.12, 5.42, 5.76, 6.18):
                _add_stereo(bed, tick, mt(ts), gain=0.25 * sfx_scale)
            _add_stereo(bed, _synth_riser(0.72, 180.0, 1200.0), mt(10.42), gain=0.45 * sfx_scale)

            pop_lo, pop_hi = _synth_pop(280.0, 580.0), _synth_pop(340.0, 700.0)
            for ts, p, pan in [
                (11.75, pop_lo, -0.25), (12.40, pop_hi, 0.25), (13.15, pop_lo, 0.0),
                (15.55, pop_lo, 0.0), (16.45, pop_hi, 0.0),
                (18.65, pop_lo, -0.30), (19.80, pop_hi, 0.30),
                (23.35, pop_lo, -0.30), (24.55, pop_hi, 0.30),
                (36.75, pop_lo, 0.20), (37.25, pop_hi, 0.20),
                (40.75, pop_lo, 0.0), (41.35, pop_hi, 0.0),
            ]:
                _add_stereo(bed, p, mt(ts), gain=0.48 * sfx_scale, pan=pan)

            _add_stereo(bed, _synth_riser(1.75, 240.0, 1400.0), mt(28.12), gain=0.42 * sfx_scale)
            _add_stereo(bed, _synth_bloom(1.55), mt(29.88), gain=0.54 * sfx_scale)
            _add_stereo(bed, _synth_ding(1174.66), mt(35.02), gain=0.46 * sfx_scale)
            _add_stereo(bed, _synth_ding(1396.91), mt(35.62), gain=0.48 * sfx_scale)
            _add_stereo(bed, _synth_bloom(1.65), mt(39.18), gain=0.46 * sfx_scale)
            _add_stereo(bed, _synth_ding(1046.50, 0.45), mt(40.05), gain=0.38 * sfx_scale)

    fi, fo = int(0.30 * SR), int(1.80 * SR)
    bed[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None]
    bed[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)[:, None]

    if enable_vo:
        if (cfg.get("template_mode") == "dynamic" or cfg.get("scenes")) and not audio_cfg.get("vo_lines"):
            audio_cfg = dict(audio_cfg)
            audio_cfg["vo_lines"] = [
                {
                    "id": sc.get("id", f"s{i + 1:02d}"),
                    "start": float(sc.get("start", 0.0)) + 0.08,
                    "max_dur": max(0.8, float(sc.get("end", 3.0)) - float(sc.get("start", 0.0)) - 0.18),
                    "text": sc.get("vo_text", ""),
                }
                for i, sc in enumerate(cfg.get("scenes") or [])
                if str(sc.get("vo_text", "")).strip()
            ]
        vo_track, duck_mask = asyncio.run(_build_vo_track(project_dir, audio_cfg, target_n))
        k = np.ones(int(0.15 * SR), dtype=np.float32) / int(0.15 * SR)
        smooth_duck = np.convolve(duck_mask, k, mode="same")
        bed_gain = (0.78 - 0.36 * smooth_duck)[:, None]
        mix = bed * bed_gain + np.stack([vo_track, vo_track], axis=1) * 1.05
        target_lufs = "-14"
    else:
        mix = bed
        target_lufs = "-15"

    pk = float(np.max(np.abs(mix)))
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
