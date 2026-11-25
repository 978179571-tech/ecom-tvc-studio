"""ecom-tvc-studio: Visual Web Studio for 16:9 & 9:16 Commercial E-Commerce Product Videos."""

import json
import mimetypes
import os
import re
import shutil
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine.audio_mixer import build_and_mux_audio
from engine.compliance import check_compliance
from engine.prompt_builder import build_prompt_pack
from engine.renderer import extract_video_frames, render_preview_grid, render_video
from engine.srt_sync import reset_scene_timings, sync_srt_to_config

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(ROOT_DIR, "projects")
TEMPLATES_DIR = os.path.join(ROOT_DIR, "templates")
WEB_DIR = os.path.join(ROOT_DIR, "web")

HOST = "127.0.0.1"
PORT = 18765

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def safe_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", raw.strip()).strip("-")
    if not cleaned:
        raise ValueError("Invalid project id")
    return cleaned


def project_path(pid: str) -> str:
    return os.path.join(PROJECTS_DIR, safe_id(pid))


def load_project_config(pid: str) -> dict:
    cfg_file = os.path.join(project_path(pid), "project.json")
    with open(cfg_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project_config(pid: str, cfg: dict):
    cfg_file = os.path.join(project_path(pid), "project.json")
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def list_projects() -> list[dict]:
    items = []
    if not os.path.exists(PROJECTS_DIR):
        return items
    for name in sorted(os.listdir(PROJECTS_DIR)):
        pdir = os.path.join(PROJECTS_DIR, name)
        cfg_file = os.path.join(pdir, "project.json")
        if os.path.isdir(pdir) and os.path.exists(cfg_file):
            try:
                cfg = json.load(open(cfg_file, encoding="utf-8"))
                items.append({
                    "id": name,
                    "name": cfg.get("project_name", name),
                    "duration": cfg.get("duration", 45.0),
                })
            except Exception:
                pass
    return items


def run_render_job(job_id: str, pid: str, ratio: str):
    pdir = project_path(pid)
    cfg = load_project_config(pid)
    template = "tvc_9x16.html" if ratio == "9x16" else "tvc_16x9.html"
    scene_url = f"http://{HOST}:{PORT}/templates/{template}?project={urllib.parse.quote(pid)}"
    out_dir = os.path.join(pdir, "out")
    os.makedirs(out_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    noaudio_mp4 = os.path.join(out_dir, f"{pid}_{ratio}_noaudio.mp4")
    final_mp4 = os.path.join(out_dir, f"{pid}_{ratio}_{ts}.mp4")

    def update(status=None, pct=None, msg=None, output_url=None, error=None):
        with JOBS_LOCK:
            j = JOBS[job_id]
            if status: j["status"] = status
            if pct is not None: j["progress"] = pct
            if msg: j["message"] = msg
            if output_url: j["output_url"] = output_url
            if error: j["error"] = error

    try:
        update(status="running", pct=2, msg="正在启动无头浏览器渲染画面...")

        def on_frame(done, total):
            pct = int(5 + (done / max(1, total)) * 80)
            update(pct=pct, msg=f"正在渲染视频帧：{done} / {total}")

        render_video(
            scene_url=scene_url,
            out_mp4=noaudio_mp4,
            ratio=ratio,
            duration=float(cfg.get("duration", 45.0)),
            fps=int(cfg.get("fps", 24)),
            progress_cb=on_frame,
        )

        update(pct=88, msg="画面渲染完成，正在合成 BGM / 五层音效 / 配音...")
        build_and_mux_audio(
            project_dir=pdir,
            cfg=cfg,
            video_noaudio=noaudio_mp4,
            out_mp4=final_mp4,
            log_cb=lambda m: update(msg=m),
        )
        rel_url = f"/projects/{urllib.parse.quote(pid)}/out/{urllib.parse.quote(os.path.basename(final_mp4))}"
        update(status="done", pct=100, msg="渲染与混音全部完成！", output_url=rel_url)
    except Exception as exc:
        update(status="error", msg=f"渲染失败：{exc}", error=str(exc))


class StudioHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, filepath: str):
        if not os.path.isfile(filepath):
            self.send_error(404, "Not Found")
            return
        ctype, _ = mimetypes.guess_type(filepath)
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(filepath, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(n) if n > 0 else b""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == "/" or path == "/index.html":
            return self._send_file(os.path.join(WEB_DIR, "index.html"))

        if path == "/api/projects":
            return self._send_json({"projects": list_projects()})

        m = re.match(r"^/api/projects/([^/]+)$", path)
        if m:
            pid = safe_id(m.group(1))
            cfg = load_project_config(pid)
            return self._send_json({
                "id": pid,
                "config": cfg,
                "compliance": check_compliance(cfg),
                "prompts": build_prompt_pack(cfg),
            })

        m = re.match(r"^/api/jobs/([^/]+)$", path)
        if m:
            jid = m.group(1)
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job:
                return self._send_json({"error": "Job not found"}, 404)
            return self._send_json(job)

        if path.startswith("/templates/"):
            rel = os.path.normpath(path[len("/templates/"):]).lstrip("\\/")
            full = os.path.abspath(os.path.join(TEMPLATES_DIR, rel))
            if full.startswith(os.path.abspath(TEMPLATES_DIR)):
                return self._send_file(full)

        if path.startswith("/projects/"):
            rel = os.path.normpath(path[len("/projects/"):]).lstrip("\\/")
            full = os.path.abspath(os.path.join(PROJECTS_DIR, rel))
            if full.startswith(os.path.abspath(PROJECTS_DIR)):
                return self._send_file(full)

        self.send_error(404, "Not Found")

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        m = re.match(r"^/api/projects/([^/]+)$", path)
        if m:
            pid = safe_id(m.group(1))
            cfg = json.loads(self._read_body().decode("utf-8"))
            save_project_config(pid, cfg)
            return self._send_json({
                "ok": True,
                "compliance": check_compliance(cfg),
                "prompts": build_prompt_pack(cfg),
            })
        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/projects":
            body = json.loads(self._read_body().decode("utf-8"))
            new_id = safe_id(body.get("id", f"proj-{int(time.time())}"))
            new_name = body.get("name", new_id)
            dst = project_path(new_id)
            if os.path.exists(dst):
                return self._send_json({"error": "项目 ID 已存在"}, 400)
            src_demo = project_path("sanjin-antang")
            shutil.copytree(src_demo, dst, ignore=shutil.ignore_patterns("out"))
            os.makedirs(os.path.join(dst, "out"), exist_ok=True)
            cfg = load_project_config(new_id)
            cfg["project_id"] = new_id
            cfg["project_name"] = new_name
            save_project_config(new_id, cfg)
            return self._send_json({"ok": True, "id": new_id})

        m = re.match(r"^/api/projects/([^/]+)/upload$", path)
        if m:
            pid = safe_id(m.group(1))
            target = (qs.get("target") or [""])[0].lstrip("/\\")
            if not target or ".." in target:
                return self._send_json({"error": "非法目标路径"}, 400)
            pdir = project_path(pid)
            raw = self._read_body()
            if target.startswith("video:"):
                frame_folder = target.split(":", 1)[1]
                if frame_folder not in ("frames_01", "frames_02", "frames_03"):
                    return self._send_json({"error": "不支持的视频槽位"}, 400)
                tmp_mp4 = os.path.join(pdir, "out", f"_upload_{frame_folder}.mp4")
                os.makedirs(os.path.dirname(tmp_mp4), exist_ok=True)
                with open(tmp_mp4, "wb") as f:
                    f.write(raw)
                cnt = extract_video_frames(tmp_mp4, os.path.join(pdir, "assets", "v5", frame_folder))
                return self._send_json({"ok": True, "frames": cnt})
            full = os.path.abspath(os.path.join(pdir, target))
            if not full.startswith(os.path.abspath(pdir)):
                return self._send_json({"error": "越权路径"}, 403)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(raw)
            return self._send_json({"ok": True, "saved": target})

        m = re.match(r"^/api/projects/([^/]+)/sync-srt$", path)
        if m:
            pid = safe_id(m.group(1))
            raw = self._read_body()
            try:
                srt_text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                srt_text = raw.decode("gbk", errors="replace")
            try:
                cfg = load_project_config(pid)
                cfg, summary = sync_srt_to_config(cfg, srt_text)
                save_project_config(pid, cfg)
                return self._send_json({
                    "ok": True,
                    "config": cfg,
                    "summary": summary,
                    "compliance": check_compliance(cfg),
                })
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 400)

        m = re.match(r"^/api/projects/([^/]+)/reset-timing$", path)
        if m:
            pid = safe_id(m.group(1))
            cfg = load_project_config(pid)
            cfg = reset_scene_timings(cfg)
            save_project_config(pid, cfg)
            return self._send_json({"ok": True, "config": cfg})

        m = re.match(r"^/api/projects/([^/]+)/preview$", path)
        if m:
            pid = safe_id(m.group(1))
            ratio = (qs.get("ratio") or ["9x16"])[0]
            template = "tvc_9x16.html" if ratio == "9x16" else "tvc_16x9.html"
            scene_url = f"http://{HOST}:{PORT}/templates/{template}?project={urllib.parse.quote(pid)}"
            out_jpg = os.path.join(project_path(pid), "out", f"preview_{ratio}.jpg")
            render_preview_grid(scene_url, out_jpg, ratio=ratio)
            return self._send_json({
                "ok": True,
                "preview_url": f"/projects/{urllib.parse.quote(pid)}/out/preview_{ratio}.jpg?ts={int(time.time())}",
            })

        m = re.match(r"^/api/projects/([^/]+)/render$", path)
        if m:
            pid = safe_id(m.group(1))
            ratio = (qs.get("ratio") or ["9x16"])[0]
            jid = uuid.uuid4().hex[:10]
            with JOBS_LOCK:
                JOBS[jid] = {"id": jid, "status": "queued", "progress": 0, "message": "已加入渲染队列..."}
            t = threading.Thread(target=run_render_job, args=(jid, pid, ratio), daemon=True)
            t.start()
            return self._send_json({"ok": True, "job_id": jid})

        self.send_error(404, "Not Found")


def main():
    print(f"\n  ecom-tvc-studio Web 工作台已启动：http://{HOST}:{PORT}\n")
    server = ThreadingHTTPServer((HOST, PORT), StudioHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止服务。")


if __name__ == "__main__":
    main()
