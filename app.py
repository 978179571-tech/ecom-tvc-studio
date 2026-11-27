"""ecom-tvc-studio 2.0: Visual Web Studio & Backend Server."""

from __future__ import annotations

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

from engine.audio_mixer import (
    CATEGORY_VOICES,
    build_and_mux_audio,
    build_preview_audio_wav,
    build_vo_timeline,
)
from engine.compliance import (
    REQUIRED_BLUE_HAT_DISCLAIMER,
    REQUIRED_DEVICE_ADVISORY,
    check_compliance,
)
from engine.prompt_builder import build_prompt_pack
from engine.ref_analyzer import analyze_reference_video
from engine.renderer import extract_video_frames, render_preview_grid, render_video_segmented
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
                    "category": cfg.get("category", "general"),
                })
            except Exception:
                pass
    return items


def resolve_template_rel(pid: str, cfg: dict, ratio: str) -> str:
    if cfg.get("template_mode") == "ref_frame":
        return f"/templates/ref_frame_studio.html?project={urllib.parse.quote(pid)}&ratio={ratio}"
    if cfg.get("template_mode") == "dynamic" or cfg.get("scenes"):
        return f"/templates/dynamic_studio.html?project={urllib.parse.quote(pid)}&ratio={ratio}"
    template = "tvc_9x16.html" if ratio == "9x16" else "tvc_16x9.html"
    return f"/templates/{template}?project={urllib.parse.quote(pid)}"


def resolve_template_file(cfg: dict, ratio: str) -> str:
    if cfg.get("template_mode") == "ref_frame":
        return os.path.join(TEMPLATES_DIR, "ref_frame_studio.html")
    if cfg.get("template_mode") == "dynamic" or cfg.get("scenes"):
        return os.path.join(TEMPLATES_DIR, "dynamic_studio.html")
    return os.path.join(TEMPLATES_DIR, "tvc_9x16.html" if ratio == "9x16" else "tvc_16x9.html")


def create_project_dir(new_id: str, new_name: str, category: str = "general", mode: str = "ref_frame") -> dict:
    dst = project_path(new_id)
    if os.path.exists(dst):
        raise ValueError(f"项目 ID 已存在：{new_id}")
    src_demo = project_path("sanjin-antang")
    if mode == "sanjin_demo":
        shutil.copytree(src_demo, dst, ignore=shutil.ignore_patterns("out"))
        os.makedirs(os.path.join(dst, "out"), exist_ok=True)
        cfg = load_project_config(new_id)
        cfg["project_id"] = new_id
        cfg["project_name"] = new_name
        cfg["category"] = category
        save_project_config(new_id, cfg)
        return cfg

    os.makedirs(os.path.join(dst, "out"), exist_ok=True)
    os.makedirs(os.path.join(dst, "assets", "official"), exist_ok=True)
    os.makedirs(os.path.join(dst, "assets", "clips"), exist_ok=True)
    os.makedirs(os.path.join(dst, "assets", "media"), exist_ok=True)
    if os.path.isdir(os.path.join(src_demo, "audio")):
        shutil.copytree(os.path.join(src_demo, "audio"), os.path.join(dst, "audio"))

    if category == "blue_hat":
        footer = REQUIRED_BLUE_HAT_DISCLAIMER
    elif category == "medical_device":
        footer = f"晋械注准XXXXXXXXXXX ｜ {REQUIRED_DEVICE_ADVISORY}"
    else:
        footer = ""

    voice = CATEGORY_VOICES.get(category, "zh-CN-YunyangNeural")
    tmode = "ref_frame" if mode == "ref_frame" else "dynamic"

    cfg = {
        "project_id": new_id,
        "project_name": new_name,
        "template_mode": tmode,
        "layout_mode": "three_band" if tmode == "ref_frame" else "fullscreen",
        "viewport_ratio": "16:9",
        "category": category,
        "duration": 26.0,
        "fps": 24,
        "frame_copy": {
            "top_left": "核心痛点直击",
            "top_right": "专研修护方案",
            "top_sub": "根源养护 源头解决",
            "bot_red": "专品专用",
            "bot_blue": "品质之选",
            "bot_line2": new_name[:9],
            "device_tag": "二类医疗器械 · 外用" if category == "medical_device" else "官方正品保障",
        },
        "brand": {
            "brand_name": new_name.split()[0] if new_name else new_id,
            "product_name": new_name,
            "category_tag": "大健康与品质消费",
            "approval_no": "",
            "function_1": "核心卖点 1",
            "function_2": "核心卖点 2",
            "compliance_footer": footer,
        },
        "scenes": [
            {
                "id": "s1_1", "frame_slot": "s1_1", "vp_mode": "clip", "type": "hero_hook",
                "trans_in": "none", "sub_style": "pain_q",
                "pain_fx": {"x0": 52.0, "y0": 75.0, "x1": 52.0, "y1": 75.0},
                "start": 0.0, "end": 3.0, "badge": "", "title": "痛点1 · 场景共鸣提问",
                "subtitle": "真实受众日常困扰", "highlight": "",
                "vo_text": "您是否还在被日常不适问题困扰？", "media": "", "items": [],
            },
            {
                "id": "s1_2", "frame_slot": "s1_2", "vp_mode": "clip", "type": "hero_hook",
                "trans_in": "whip_zoom", "sub_style": "pain_stomp3",
                "pain_fx": {"x0": 55.0, "y0": 76.0, "x1": 55.0, "y1": 76.0},
                "start": 3.0, "end": 6.5, "badge": "", "title": "痛点2 · 三连症状暴击",
                "subtitle": "三大典型痛感卡点弹出", "highlight": "",
                "vo_text": "反复不适、状态紧绷、活动受限，", "media": "", "items": [],
            },
            {
                "id": "s2_1", "frame_slot": "s2_1", "vp_mode": "clip", "type": "proof_spec",
                "trans_in": "optical_flash", "sub_style": "pro_glass",
                "start": 6.5, "end": 11.5, "badge": "", "title": "产品亮相 · 官方多图参考动态展台",
                "subtitle": "外盒+内包装+产品本体流光亮相", "highlight": "",
                "vo_text": f"这款{new_name}，独立锁鲜包装，专为日常养护研发。", "media": "", "items": [],
            },
            {
                "id": "s3", "frame_slot": "s3", "vp_mode": "clip", "type": "data_hud",
                "trans_in": "dissolve", "sub_style": "pro_glass",
                "start": 11.5, "end": 17.0, "badge": "", "title": "微观机理 · 3D超微距可视化",
                "subtitle": "核心结构与活性渗透演示", "highlight": "",
                "vo_text": "核心专研配方搭配温和亲肤工艺，深入渗透，舒适好吸收。", "media": "", "items": [],
            },
            {
                "id": "s4", "frame_slot": "s4", "vp_mode": "coverflow3", "type": "orbit_cards",
                "trans_in": "dissolve", "sub_style": "pro_glass",
                "start": 17.0, "end": 22.5, "badge": "多场景适用人群", "title": "3D轮播 · 多场景适用",
                "subtitle": "三类核心受众依次C位放大", "highlight": "",
                "vo_text": "无论是日常居家护理；还是运动后放松；外出常备，都适用。", "media": "",
                "items": [
                    {"title": "居家日常养护", "frame_slot": "s4_1", "px": 50, "py": 66},
                    {"title": "运动活力呵护", "frame_slot": "s4_2", "px": 50, "py": 70},
                    {"title": "职场出行常备", "frame_slot": "s4_3", "px": 50, "py": 66},
                ],
            },
            {
                "id": "s5", "frame_slot": "s5", "vp_mode": "clip", "type": "brand_finale",
                "trans_in": "dissolve", "sub_style": "pro_glass",
                "start": 22.5, "end": 26.0, "badge": "", "title": "舒缓落版 · 状态轻松自如",
                "subtitle": "恢复轻盈活力状态", "highlight": "",
                "vo_text": "温和呵护每一天，让状态更轻松自如。", "media": "", "items": [],
            },
        ],
        "audio": {
            "enable_bgm": True,
            "enable_sfx": True,
            "enable_vo": True,
            "voice": voice,
            "voice_rate": "+0%",
            "use_cached_vo": True,
            "no_atempo": True,
            "bgm_gain": 0.43,
            "sfx_scale": 0.95,
            "vo_lines": [],
        },
    }
    save_project_config(new_id, cfg)
    return cfg


def run_render_job(job_id: str, pid: str, ratio: str, force_full: bool = False):
    pdir = project_path(pid)
    cfg = load_project_config(pid)
    scene_url = f"http://{HOST}:{PORT}{resolve_template_rel(pid, cfg, ratio)}"
    tpl_file = resolve_template_file(cfg, ratio)
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
        update(status="running", pct=3, msg="正在比对分段缓存并启动渲染引擎...")

        def on_frame(done, total):
            pct = int(6 + (done / max(1, total)) * 80)
            update(pct=pct, msg=f"正在渲染变更帧：{done} / {total}")

        seg_stat = render_video_segmented(
            project_dir=pdir,
            tpl_file=tpl_file,
            cfg=cfg,
            scene_url=scene_url,
            out_mp4=noaudio_mp4,
            ratio=ratio,
            fps=int(cfg.get("fps", 24)),
            force_full=force_full,
            progress_cb=on_frame,
        )

        update(pct=88, msg=f"画面完成（重渲 {seg_stat['rendered_scenes']} 镜 / 缓存复用 {seg_stat['cached_scenes']} 镜），正在混音...")
        build_and_mux_audio(
            project_dir=pdir,
            cfg=cfg,
            video_noaudio=noaudio_mp4,
            out_mp4=final_mp4,
            log_cb=lambda m: update(msg=m),
        )
        shutil.copyfile(final_mp4, os.path.join(out_dir, f"{pid}_{ratio}_latest.mp4"))
        rel_url = f"/projects/{urllib.parse.quote(pid)}/out/{urllib.parse.quote(os.path.basename(final_mp4))}"
        update(
            status="done",
            pct=100,
            msg=f"⚡ 出片完成！（重渲 {seg_stat['rendered_scenes']} 镜，秒级复用 {seg_stat['cached_scenes']} 镜缓存）",
            output_url=rel_url,
        )
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
            pdir = project_path(pid)
            cfg = load_project_config(pid)
            mix_wav = os.path.join(pdir, "out", "_mix_master.wav")
            audio_url = f"/projects/{urllib.parse.quote(pid)}/out/_mix_master.wav?ts={int(os.path.getmtime(mix_wav))}" if os.path.exists(mix_wav) else ""
            return self._send_json({
                "id": pid,
                "config": cfg,
                "audio_url": audio_url,
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
            category = body.get("category", "general")
            mode = body.get("mode", "ref_frame")
            try:
                create_project_dir(new_id, new_name, category=category, mode=mode)
            except ValueError as exc:
                return self._send_json({"error": str(exc)}, 400)
            return self._send_json({"ok": True, "id": new_id})

        m = re.match(r"^/api/projects/([^/]+)/build-vo$", path)
        if m:
            pid = safe_id(m.group(1))
            pdir = project_path(pid)
            try:
                cfg = load_project_config(pid)
                vo_res = build_vo_timeline(pdir, cfg)
                save_project_config(pid, cfg)
                wav_path = build_preview_audio_wav(pdir, cfg)
                return self._send_json({
                    "ok": True,
                    "config": cfg,
                    "vo_report": vo_res,
                    "audio_url": f"/projects/{urllib.parse.quote(pid)}/out/_mix_master.wav?ts={int(os.path.getmtime(wav_path))}",
                    "compliance": check_compliance(cfg),
                    "prompts": build_prompt_pack(cfg),
                })
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 400)

        m = re.match(r"^/api/projects/([^/]+)/preview-audio$", path)
        if m:
            pid = safe_id(m.group(1))
            pdir = project_path(pid)
            try:
                cfg = load_project_config(pid)
                wav_path = build_preview_audio_wav(pdir, cfg)
                return self._send_json({
                    "ok": True,
                    "audio_url": f"/projects/{urllib.parse.quote(pid)}/out/_mix_master.wav?ts={int(os.path.getmtime(wav_path))}",
                })
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 400)

        m = re.match(r"^/api/projects/([^/]+)/analyze-ref$", path)
        if m:
            pid = safe_id(m.group(1))
            pdir = project_path(pid)
            raw = self._read_body()
            ref_dir = os.path.join(pdir, "out", "_ref")
            os.makedirs(ref_dir, exist_ok=True)
            ref_mp4 = os.path.join(ref_dir, "reference.mp4")
            with open(ref_mp4, "wb") as f:
                f.write(raw)
            extract_bgm = (qs.get("extract_audio") or ["1"])[0] == "1"
            bgm_dst = os.path.join(ref_dir, "ref_audio.wav") if extract_bgm else None
            try:
                analysis = analyze_reference_video(ref_mp4, ref_dir, extract_audio_path=bgm_dst)
                cfg = load_project_config(pid)
                lc = analysis.get("layout_contract") or {}
                if lc.get("is_three_band_frame"):
                    cfg["template_mode"] = "ref_frame"
                    cfg["layout_mode"] = "three_band"
                    cfg["viewport_ratio"] = lc.get("recommended_1080x1920_contract", {}).get("viewport_ratio", "16:9")
                else:
                    cfg["template_mode"] = "ref_frame"
                    cfg["layout_mode"] = "fullscreen"
                cfg["duration"] = analysis["meta"]["duration"]
                cfg["scenes"] = analysis["suggested_scenes"]
                save_project_config(pid, cfg)
                return self._send_json({
                    "ok": True,
                    "config": cfg,
                    "analysis": {
                        "meta": analysis["meta"],
                        "layout_contract": lc,
                        "scene_count": analysis["scene_count"],
                        "cuts": analysis["cuts"],
                        "storyboard_url": f"/projects/{urllib.parse.quote(pid)}/out/_ref/ref_storyboard.jpg?ts={int(time.time())}",
                    },
                    "compliance": check_compliance(cfg),
                    "prompts": build_prompt_pack(cfg),
                })
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 400)

        m = re.match(r"^/api/projects/([^/]+)/upload$", path)
        if m:
            pid = safe_id(m.group(1))
            target = (qs.get("target") or [""])[0].lstrip("/\\")
            if not target or ".." in target:
                return self._send_json({"error": "非法目标路径"}, 400)
            pdir = project_path(pid)
            raw = self._read_body()
            if target.startswith("clip:"):
                slot = safe_id(target.split(":", 1)[1]).replace("-", "_")
                tmp_mp4 = os.path.join(pdir, "out", f"_upload_clip_{slot}.mp4")
                os.makedirs(os.path.dirname(tmp_mp4), exist_ok=True)
                with open(tmp_mp4, "wb") as f:
                    f.write(raw)
                cfg = load_project_config(pid)
                sc_match = next((s for s in (cfg.get("scenes") or []) if (s.get("frame_slot") or s.get("id")) == slot), None)
                t_dur = (float(sc_match["end"]) - float(sc_match["start"]) + 0.35) if sc_match else 0.0
                cnt = extract_video_frames(
                    tmp_mp4,
                    os.path.join(pdir, "assets", "clips", slot),
                    width=1280,
                    height=720,
                    loop_tail="auto",
                    target_dur=t_dur,
                )
                if sc_match is not None:
                    sc_match["clip_frames"] = cnt
                    save_project_config(pid, cfg)
                return self._send_json({"ok": True, "slot": slot, "frames": cnt})
            if target.startswith("video:"):
                frame_folder = target.split(":", 1)[1]
                if frame_folder not in ("frames_01", "frames_02", "frames_03"):
                    return self._send_json({"error": "不支持的视频槽位"}, 400)
                tmp_mp4 = os.path.join(pdir, "out", f"_upload_{frame_folder}.mp4")
                os.makedirs(os.path.dirname(tmp_mp4), exist_ok=True)
                with open(tmp_mp4, "wb") as f:
                    f.write(raw)
                cnt = extract_video_frames(tmp_mp4, os.path.join(pdir, "assets", "v5", frame_folder), width=1920, height=1080)
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
            cfg = load_project_config(pid)
            scene_url = f"http://{HOST}:{PORT}{resolve_template_rel(pid, cfg, ratio)}"
            out_jpg = os.path.join(project_path(pid), "out", f"preview_{ratio}.jpg")
            render_preview_grid(scene_url, out_jpg, ratio=ratio, scenes=cfg.get("scenes"))
            return self._send_json({
                "ok": True,
                "preview_url": f"/projects/{urllib.parse.quote(pid)}/out/preview_{ratio}.jpg?ts={int(time.time())}",
            })

        m = re.match(r"^/api/projects/([^/]+)/render$", path)
        if m:
            pid = safe_id(m.group(1))
            ratio = (qs.get("ratio") or ["9x16"])[0]
            force_full = (qs.get("full") or ["0"])[0] == "1"
            jid = uuid.uuid4().hex[:10]
            with JOBS_LOCK:
                JOBS[jid] = {"id": jid, "status": "queued", "progress": 0, "message": "已加入分段极速渲染队列..."}
            t = threading.Thread(target=run_render_job, args=(jid, pid, ratio, force_full), daemon=True)
            t.start()
            return self._send_json({"ok": True, "job_id": jid})

        self.send_error(404, "Not Found")


def main():
    print(f"\n  ecom-tvc-studio 2.0 Web 工作台已启动：http://{HOST}:{PORT}\n")
    server = ThreadingHTTPServer((HOST, PORT), StudioHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止服务。")


if __name__ == "__main__":
    main()
