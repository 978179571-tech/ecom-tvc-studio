"""Unified 16:9 & 9:16 Headless Edge CDP + Incremental Segment-Cached FFmpeg Renderer (2.0).

New in 2.0:
  1. `extract_video_frames(..., trim_start, trim_dur, loop_tail, target_dur)`:
     Supports `--loop-tail auto` or `--loop-tail 3.4:5.9` local ping-pong loop so short AI clips
     cover long natural-VO scenes at genuine 24fps without stutter or backward-walking artifacts.
  2. `audit_ai_library(lib_dir, out_sheet_jpg)`:
     Scans `AI素材库`, probes resolution/ratio/fps/duration, and builds a 3-frame-per-clip visual QA sheet.
  3. `render_video_segmented(...)`:
     Per-scene SHA-1 segment cache (`out/_segments/`). Modifying 1 scene's copy, pain coordinate,
     or video clip re-renders ONLY that single 3-6s scene (~5s) and losslessly concats the full MP4!
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from PIL import Image, ImageDraw, ImageFont

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def find_browser() -> str:
    for path in EDGE_CANDIDATES:
        if os.path.exists(path):
            return path
    raise RuntimeError("未找到 Microsoft Edge 或 Google Chrome，请安装后重试。")


def probe_clip_info(mp4_path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate:format=duration",
        "-of", "json", mp4_path,
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    st = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    w = int(st.get("width", 1280))
    h = int(st.get("height", 720))
    dur = float(fmt.get("duration", st.get("duration", 4.0) or 4.0))
    r_str = str(st.get("r_frame_rate", "24/1"))
    fps = round(float(r_str.split("/")[0]) / max(1.0, float(r_str.split("/")[1])), 2) if "/" in r_str else float(r_str)
    ratio = "9:16" if h > w * 1.15 else ("16:9" if w > h * 1.15 else "1:1")
    return {"width": w, "height": h, "duration": round(dur, 3), "fps": fps, "ratio": ratio}


def extract_video_frames(
    mp4_path: str,
    out_dir: str,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
    trim_start: float = 0.0,
    trim_dur: float | None = None,
    loop_tail: str | None = None,
    target_dur: float = 0.0,
) -> int:
    """Extract 24fps JPEG frames with optional trim & local stationary-tail ping-pong loop."""
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".jpg"):
            os.remove(os.path.join(out_dir, f))

    info = probe_clip_info(mp4_path)
    avail_dur = max(0.5, info["duration"] - trim_start)
    if trim_dur is not None:
        avail_dur = min(avail_dur, float(trim_dur))

    scale_crop = f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height}"

    # Determine ping-pong tail window if requested or if target_dur exceeds available clip length
    tail_pair = None
    if loop_tail:
        lt = str(loop_tail).strip().lower()
        if lt == "auto" and target_dur > avail_dur + 0.1:
            t_a = round(max(0.5, avail_dur * 0.52), 2)
            t_b = round(max(t_a + 0.4, avail_dur - 0.05), 2)
            tail_pair = (t_a, t_b)
        elif ":" in lt:
            p1, p2 = lt.split(":", 1)
            tail_pair = (float(p1), float(p2))

    cmd = ["ffmpeg", "-y", "-v", "error"]
    if trim_start > 0:
        cmd += ["-ss", f"{trim_start:.3f}"]
    if trim_dur is not None:
        cmd += ["-t", f"{trim_dur:.3f}"]
    cmd += ["-i", mp4_path]

    if tail_pair:
        ta, tb = tail_pair
        vf = (
            f"[0:v]{scale_crop},split[f][r];"
            f"[r]trim={ta:.2f}:{tb:.2f},reverse,setpts=PTS-STARTPTS[rev];"
            f"[f][rev]concat=n=2:v=1:a=0,fps={fps}"
        )
        cmd += ["-filter_complex", vf, "-q:v", "2", os.path.join(out_dir, "f_%04d.jpg")]
    else:
        cmd += ["-vf", f"fps={fps},{scale_crop}", "-q:v", "2", os.path.join(out_dir, "f_%04d.jpg")]

    subprocess.check_call(cmd)
    return len([f for f in os.listdir(out_dir) if f.endswith(".jpg")])


def audit_ai_library(lib_dir: str, out_sheet_jpg: str | None = None) -> dict:
    """Scan all video files in `AI素材库` and generate metadata + visual QA contact sheet."""
    if not os.path.isdir(lib_dir):
        raise FileNotFoundError(f"素材目录不存在：{lib_dir}")

    videos = sorted([
        f for f in os.listdir(lib_dir)
        if f.lower().endswith((".mp4", ".mov", ".webm"))
    ])
    items = []
    thumbs: list[tuple[str, list[Image.Image]]] = []

    tmp_dir = tempfile.mkdtemp(prefix="ai_lib_audit_")
    for idx, fn in enumerate(videos):
        full = os.path.join(lib_dir, fn)
        info = probe_clip_info(full)
        warnings = []
        if info["duration"] < 3.5:
            warnings.append("时长偏短(<3.5s)，长口播需开启 --loop-tail 循环")
        entry = {"file": fn, "path": full, **info, "warnings": warnings}
        items.append(entry)

        if out_sheet_jpg:
            sub_ims = []
            for si, pct in enumerate((0.18, 0.52, 0.85)):
                ts = max(0.0, info["duration"] * pct)
                tp = os.path.join(tmp_dir, f"v{idx}_{si}.jpg")
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.2f}", "-i", full, "-vframes", "1", "-q:v", "3", tp],
                    check=False,
                )
                if os.path.exists(tp):
                    sub_ims.append(Image.open(tp).convert("RGB"))
            if sub_ims:
                thumbs.append((f"{fn[:28]} ({info['ratio']} · {info['duration']:.1f}s)", sub_ims))

    if out_sheet_jpg and thumbs:
        os.makedirs(os.path.dirname(out_sheet_jpg), exist_ok=True)
        tw, th, pad, hdr_h = 280, 168, 10, 28
        sheet_w = 3 * tw + 4 * pad
        sheet_h = len(thumbs) * (th + hdr_h + pad) + pad
        sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 24, 32))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 16)
        except Exception:
            font = ImageFont.load_default()
        for ri, (title, ims) in enumerate(thumbs):
            y0 = pad + ri * (th + hdr_h + pad)
            draw.text((pad, y0 + 4), title, fill=(255, 224, 102), font=font)
            for ci, im in enumerate(ims[:3]):
                x0 = pad + ci * (tw + pad)
                im_fit = im.copy()
                im_fit.thumbnail((tw, th), Image.Resampling.LANCZOS)
                bg = Image.new("RGB", (tw, th), (10, 14, 20))
                bg.paste(im_fit, ((tw - im_fit.width) // 2, (th - im_fit.height) // 2))
                sheet.paste(bg, (x0, y0 + hdr_h))
                im.close()
        sheet.save(out_sheet_jpg, "JPEG", quality=88)

    return {"count": len(items), "audit_sheet_jpg": out_sheet_jpg, "clips": items}


class SimpleCDP:
    def __init__(self, ws_url: str):
        rest = ws_url[5:]
        host_port, path = rest.split("/", 1)
        host, port = host_port.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET /{path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode("ascii"))
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        self._buf = resp.split(b"\r\n\r\n", 1)[1]
        self._id = 0

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("WebSocket EOF")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def _send_text(self, text: str):
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_frame(self) -> str:
        while True:
            b1, b2 = self._recv_exact(2)
            opcode = b1 & 0x0F
            masked = (b2 & 0x80) != 0
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else None
            payload = self._recv_exact(length)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                raise RuntimeError("WebSocket closed")
            if opcode == 0x9:
                self.sock.sendall(b"\x8a\x80\x00\x00\x00\x00")
                continue
            if opcode in (0x1, 0x2):
                return payload.decode("utf-8")

    def call(self, method: str, params=None) -> dict:
        self._id += 1
        cid = self._id
        self._send_text(json.dumps({"id": cid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self._recv_frame())
            if msg.get("id") == cid:
                return msg.get("result", {})

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def _launch_browser(width: int, height: int):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    user_dir = tempfile.mkdtemp(prefix="ecom_tvc_cdp_")
    proc = subprocess.Popen(
        [
            find_browser(),
            "--headless=new",
            "--disable-gpu-sandbox",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_dir}",
            f"--window-size={width},{height}",
            "--hide-scrollbars",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ws_url = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as r:
                pages = json.loads(r.read().decode("utf-8"))
                for p in pages:
                    if p.get("type") == "page" and "webSocketDebuggerUrl" in p:
                        ws_url = p["webSocketDebuggerUrl"]
                        break
            if ws_url:
                break
        except Exception:
            time.sleep(0.15)
    if not ws_url:
        proc.kill()
        raise RuntimeError("无法连接无头浏览器 CDP 端口。")
    return proc, ws_url


def _setup_page(cdp: SimpleCDP, scene_url: str, width: int, height: int):
    cdp.call("Page.enable")
    cdp.call("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False
    })
    cdp.call("Page.navigate", {"url": scene_url})
    for _ in range(80):
        res = cdp.call("Runtime.evaluate", {
            "expression": "document.readyState === 'complete' && typeof window.renderAt === 'function' && Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)",
            "returnByValue": True,
        })
        if res.get("result", {}).get("value") is True:
            break
        time.sleep(0.15)
    cdp.call("Runtime.evaluate", {"expression": "document.fonts.ready.then(() => true)", "awaitPromise": True, "returnByValue": True})
    time.sleep(0.15)


def _capture(cdp: SimpleCDP, t: float, fmt: str = "jpeg", quality: int = 94) -> bytes:
    cdp.call("Runtime.evaluate", {
        "expression": f"Promise.resolve(window.renderAt({t:.4f})).then(() => true)",
        "awaitPromise": True,
        "returnByValue": True,
    })
    params = {"format": fmt}
    if fmt == "jpeg":
        params["quality"] = quality
    return base64.b64decode(cdp.call("Page.captureScreenshot", params)["data"])


def render_preview_grid(scene_url: str, out_jpg: str, ratio: str = "9x16", scenes: list[dict] | None = None) -> str:
    width, height = (1080, 1920) if ratio == "9x16" else (1920, 1080)
    if scenes:
        keyframes = []
        for idx, sc in enumerate(scenes):
            st = float(sc.get("start", 0.0))
            en = float(sc.get("end", st + 3.0))
            mid = round(st + (en - st) * 0.52, 2)
            lbl = f"{sc.get('id', f'S{idx+1}')} {mid:.1f}s {str(sc.get('title', ''))[:8]}"
            keyframes.append((mid, lbl))
    else:
        keyframes = [(1.80, "S1 1.8s"), (5.50, "S2 5.5s"), (13.80, "S3 13.8s")]

    os.makedirs(os.path.dirname(out_jpg), exist_ok=True)
    proc, ws_url = _launch_browser(width, height)
    frames = []
    try:
        cdp = SimpleCDP(ws_url)
        _setup_page(cdp, scene_url, width, height)
        for t, label in keyframes:
            raw = _capture(cdp, t, fmt="png")
            frames.append((raw, label))
        cdp.close()
    finally:
        proc.kill()

    tw, th = (270, 480) if ratio == "9x16" else (560, 315)
    cols = min(len(frames), 6 if ratio == "9x16" else 4) or 1
    rows = (len(frames) + cols - 1) // cols
    pad, bar_h = 12, 32
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * pad, rows * (th + bar_h) + (rows + 1) * pad), (24, 34, 31))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 18)
    except Exception:
        font = ImageFont.load_default()
    for idx, (raw, label) in enumerate(frames):
        r, c = divmod(idx, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + bar_h + pad)
        im = Image.open(io.BytesIO(raw)).convert("RGB").resize((tw, th), Image.Resampling.LANCZOS)
        sheet.paste(im, (x, y))
        draw.rectangle([x, y + th, x + tw, y + th + bar_h], fill=(16, 62, 52))
        draw.text((x + 10, y + th + 5), label, fill=(255, 224, 102), font=font)
    sheet.save(out_jpg, "JPEG", quality=92)
    return out_jpg


def _slot_fingerprint(project_dir: str, slot: str) -> str:
    if not slot:
        return ""
    d = os.path.join(project_dir, "assets", "clips", slot)
    if not os.path.isdir(d):
        return "missing"
    jpgs = [f for f in os.listdir(d) if f.endswith(".jpg")]
    if not jpgs:
        return "empty"
    f1 = os.path.join(d, sorted(jpgs)[0])
    return f"{len(jpgs)}:{int(os.path.getmtime(f1))}"


def _scene_cache_sig(project_dir: str, tpl_file: str, cfg: dict, idx: int, ratio: str, fps: int, f0: int, f1: int) -> str:
    scenes = cfg.get("scenes") or []
    sc = scenes[idx]
    prev_sc = scenes[idx - 1] if idx > 0 else None
    next_sc = scenes[idx + 1] if idx + 1 < len(scenes) else None

    slots = [sc.get("frame_slot") or sc.get("id", "")]
    for it in (sc.get("items") or []):
        if isinstance(it, dict) and it.get("frame_slot"):
            slots.append(it["frame_slot"])
    if prev_sc:
        slots.append(prev_sc.get("frame_slot") or prev_sc.get("id", ""))
    if sc.get("pip_loupe") and isinstance(sc["pip_loupe"], dict):
        slots.append(sc["pip_loupe"].get("frame_slot", ""))
    if sc.get("wipe_compare") and isinstance(sc["wipe_compare"], dict):
        slots.append(sc["wipe_compare"].get("before_slot", ""))
        slots.append(sc["wipe_compare"].get("after_slot", ""))

    tpl_mtime = int(os.path.getmtime(tpl_file)) if os.path.exists(tpl_file) else 0
    payload = {
        "tpl_mtime": tpl_mtime,
        "ratio": ratio,
        "fps": fps,
        "f_range": [f0, f1],
        "layout_mode": cfg.get("layout_mode", "three_band"),
        "viewport_ratio": cfg.get("viewport_ratio", "16:9"),
        "frame_copy": cfg.get("frame_copy"),
        "brand": cfg.get("brand"),
        "sc": sc,
        "prev_id": prev_sc.get("id") if prev_sc else None,
        "next_trans": next_sc.get("trans_in") if next_sc else None,
        "slots": {s: _slot_fingerprint(project_dir, s) for s in slots if s},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:14]


def render_video_segmented(
    project_dir: str,
    tpl_file: str,
    cfg: dict,
    scene_url: str,
    out_mp4: str,
    ratio: str = "9x16",
    fps: int = 24,
    force_full: bool = False,
    progress_cb=None,
) -> dict:
    """Incremental segment-cached renderer: only renders changed scenes and concats losslessly!"""
    scenes = cfg.get("scenes") or []
    duration = float(cfg.get("duration", 45.0))
    if not scenes:
        render_video(scene_url, out_mp4, ratio=ratio, duration=duration, fps=fps, progress_cb=progress_cb)
        return {"rendered_scenes": 1, "cached_scenes": 0, "total_scenes": 1}

    width, height = (1080, 1920) if ratio == "9x16" else (1920, 1080)
    total_frames = int(round(duration * fps))
    seg_dir = os.path.join(project_dir, "out", "_segments")
    os.makedirs(seg_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)

    plan = []
    for idx, sc in enumerate(scenes):
        st = float(sc.get("start", 0.0))
        en = float(sc.get("end", duration)) if idx < len(scenes) - 1 else duration
        f0 = int(round(st * fps))
        f1 = total_frames if idx == len(scenes) - 1 else int(round(en * fps))
        if f1 <= f0:
            continue
        sig = _scene_cache_sig(project_dir, tpl_file, cfg, idx, ratio, fps, f0, f1)
        seg_mp4 = os.path.join(seg_dir, f"s{idx:02d}_{sc.get('id', idx)}_{ratio}_{sig}.mp4")
        cached = (not force_full) and os.path.exists(seg_mp4) and os.path.getsize(seg_mp4) > 1024
        plan.append((idx, sc.get("id", f"s{idx}"), f0, f1, seg_mp4, cached))

    dirty = [p for p in plan if not p[5]]
    frames_to_do = sum(p[3] - p[2] for p in dirty)
    done_so_far = 0

    if dirty:
        proc, ws_url = _launch_browser(width, height)
        try:
            cdp = SimpleCDP(ws_url)
            _setup_page(cdp, scene_url, width, height)
            for idx, sid, f0, f1, seg_mp4, _ in dirty:
                tmp_seg = seg_mp4 + ".part.mp4"
                ff = subprocess.Popen(
                    [
                        "ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-vcodec", "mjpeg",
                        "-framerate", str(fps), "-i", "-",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17",
                        "-preset", "fast", "-g", str(fps), tmp_seg,
                    ],
                    stdin=subprocess.PIPE,
                )
                try:
                    for fi in range(f0, f1):
                        ff.stdin.write(_capture(cdp, fi / fps, fmt="jpeg", quality=94))
                        done_so_far += 1
                        if progress_cb and (done_so_far % 8 == 0 or done_so_far == frames_to_do):
                            progress_cb(done_so_far, frames_to_do)
                finally:
                    ff.stdin.close()
                    ff.wait()
                if os.path.exists(tmp_seg):
                    os.replace(tmp_seg, seg_mp4)
            cdp.close()
        finally:
            proc.kill()
    else:
        if progress_cb:
            progress_cb(1, 1)

    concat_txt = os.path.join(seg_dir, f"_concat_{ratio}.txt")
    with open(concat_txt, "w", encoding="utf-8") as cf:
        for _, _, _, _, seg_mp4, _ in plan:
            safe_p = seg_mp4.replace("\\", "/")
            cf.write(f"file '{safe_p}'\n")

    subprocess.check_call([
        "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
        "-i", concat_txt, "-c", "copy", "-movflags", "+faststart", out_mp4,
    ])
    return {
        "rendered_scenes": len(dirty),
        "cached_scenes": len(plan) - len(dirty),
        "total_scenes": len(plan),
        "rendered_scene_ids": [p[1] for p in dirty],
    }


def render_video(scene_url: str, out_mp4: str, ratio: str = "9x16", duration: float = 45.0, fps: int = 24, progress_cb=None) -> str:
    width, height = (1080, 1920) if ratio == "9x16" else (1920, 1080)
    total_frames = int(round(duration * fps))
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    ff = subprocess.Popen(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-vcodec", "mjpeg",
            "-framerate", str(fps), "-i", "-",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17",
            "-preset", "medium", "-movflags", "+faststart", out_mp4,
        ],
        stdin=subprocess.PIPE,
    )
    proc, ws_url = _launch_browser(width, height)
    try:
        cdp = SimpleCDP(ws_url)
        _setup_page(cdp, scene_url, width, height)
        for idx in range(total_frames):
            ff.stdin.write(_capture(cdp, idx / fps, fmt="jpeg", quality=94))
            if progress_cb and ((idx + 1) % 12 == 0 or idx == total_frames - 1):
                progress_cb(idx + 1, total_frames)
        cdp.close()
    finally:
        proc.kill()
        ff.stdin.close()
        ff.wait()
    return out_mp4
