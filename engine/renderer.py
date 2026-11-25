"""Unified 16:9 & 9:16 Headless Edge CDP + FFmpeg Renderer & Video Frame Extractor."""

import base64
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


def extract_video_frames(mp4_path: str, out_dir: str, fps: int = 24) -> int:
    """Extract 1920x1080 24fps JPEG frames from an uploaded pain-point MP4."""
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".jpg"):
            os.remove(os.path.join(out_dir, f))
    subprocess.check_call([
        "ffmpeg", "-y", "-v", "error", "-i", mp4_path,
        "-vf", f"fps={fps},scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080",
        "-q:v", "2", os.path.join(out_dir, "f_%04d.jpg"),
    ])
    return len([f for f in os.listdir(out_dir) if f.endswith(".jpg")])


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
        keyframes = [
            (1.80, "S1 1.8s 痛点1"),
            (5.50, "S2A 5.5s 痛点2"),
            (9.20, "S2B 9.2s 痛点3"),
            (13.80, "S3 13.8s 透视仪"),
            (17.00, "S4 17.0s 单钙对比"),
            (21.00, "S5A 21.0s 营养1"),
            (25.60, "S5B 25.6s 营养2"),
            (29.10, "S5C 29.1s 注入"),
            (31.25, "S5C 31.2s 舒展"),
            (36.80, "S6 36.8s 蓝帽规格"),
            (42.50, "S7 42.5s 落版"),
        ]
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
    import io
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
