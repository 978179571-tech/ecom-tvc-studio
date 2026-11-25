"""Agent-Native CLI for ecom-tvc-studio (supports deterministic JSON output for AI Agents)."""

import argparse
import json
import os
import shutil
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer

from app import HOST, PORT, StudioHandler, list_projects, load_project_config, project_path, safe_id, save_project_config
from engine.audio_mixer import build_and_mux_audio
from engine.compliance import check_compliance
from engine.prompt_builder import build_prompt_pack
from engine.renderer import extract_video_frames, render_preview_grid, render_video
from engine.srt_sync import reset_scene_timings, sync_srt_to_config


def _with_temp_server(fn):
    """Run an ephemeral local HTTP server on a free port so headless Edge can load templates."""
    server = ThreadingHTTPServer((HOST, 0), StudioHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        return fn(port)
    finally:
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(prog="ecom-tvc-studio", description="Agent-Native + Human-in-the-Loop E-Commerce Video Studio CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all projects")

    p_init = sub.add_parser("init", help="Create a new project cloned from demo")
    p_init.add_argument("--id", required=True)
    p_init.add_argument("--name", required=True)

    p_chk = sub.add_parser("check", help="Run blue-hat compliance check")
    p_chk.add_argument("--project", required=True)

    p_pr = sub.add_parser("prompts", help="Generate Chinese image & video prompts")
    p_pr.add_argument("--project", required=True)

    p_iv = sub.add_parser("ingest-video", help="Extract 24fps 1920x1080 frames from a pain-point MP4")
    p_iv.add_argument("--project", required=True)
    p_iv.add_argument("--slot", required=True, choices=["frames_01", "frames_02", "frames_03"])
    p_iv.add_argument("--file", required=True)

    p_srt = sub.add_parser("sync-srt", help="Parse an .srt file and auto-align 10 scenes, duration & VO lines")
    p_srt.add_argument("--project", required=True)
    p_srt.add_argument("--srt", required=True, help="Path to .srt subtitle file")

    p_rst = sub.add_parser("reset-timing", help="Reset custom SRT scene timings back to default 45s timeline")
    p_rst.add_argument("--project", required=True)

    p_pv = sub.add_parser("preview", help="Render 11-frame contact sheet preview")
    p_pv.add_argument("--project", required=True)
    p_pv.add_argument("--ratio", default="9x16", choices=["9x16", "16x9"])

    p_rd = sub.add_parser("render", help="Render full MP4 + 3-layer audio mix")
    p_rd.add_argument("--project", required=True)
    p_rd.add_argument("--ratio", default="9x16", choices=["9x16", "16x9"])
    p_rd.add_argument("--out", default="", help="Optional custom output MP4 path")

    p_st = sub.add_parser("studio", help="Launch Visual Web Studio for human preview & editing")
    p_st.add_argument("--port", type=int, default=PORT)

    args = parser.parse_args()

    if args.cmd == "list":
        print(json.dumps({"projects": list_projects()}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "init":
        pid = safe_id(args.id)
        dst = project_path(pid)
        if os.path.exists(dst):
            raise SystemExit(f"Project already exists: {pid}")
        shutil.copytree(project_path("sanjin-antang"), dst, ignore=shutil.ignore_patterns("out"))
        os.makedirs(os.path.join(dst, "out"), exist_ok=True)
        cfg = load_project_config(pid)
        cfg["project_id"] = pid
        cfg["project_name"] = args.name
        save_project_config(pid, cfg)
        print(json.dumps({"ok": True, "project_id": pid, "config_path": os.path.join(dst, "project.json")}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "check":
        cfg = load_project_config(args.project)
        res = check_compliance(cfg)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if not res["passed"]:
            raise SystemExit(2)
        return

    if args.cmd == "prompts":
        cfg = load_project_config(args.project)
        print(json.dumps({"prompts": build_prompt_pack(cfg)}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "ingest-video":
        pdir = project_path(args.project)
        cnt = extract_video_frames(args.file, os.path.join(pdir, "assets", "v5", args.slot))
        print(json.dumps({"ok": True, "slot": args.slot, "frames": cnt}, ensure_ascii=False))
        return

    if args.cmd == "sync-srt":
        pid = safe_id(args.project)
        cfg = load_project_config(pid)
        with open(args.srt, "rb") as f:
            raw = f.read()
        try:
            srt_text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            srt_text = raw.decode("gbk", errors="replace")
        cfg, summary = sync_srt_to_config(cfg, srt_text)
        save_project_config(pid, cfg)
        print(json.dumps({"ok": True, "project_id": pid, **summary}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "reset-timing":
        pid = safe_id(args.project)
        cfg = load_project_config(pid)
        cfg = reset_scene_timings(cfg)
        save_project_config(pid, cfg)
        print(json.dumps({"ok": True, "project_id": pid, "duration": cfg["duration"]}, ensure_ascii=False))
        return

    if args.cmd == "preview":
        pid = safe_id(args.project)
        tpl = "tvc_9x16.html" if args.ratio == "9x16" else "tvc_16x9.html"
        out_jpg = os.path.join(project_path(pid), "out", f"preview_{args.ratio}.jpg")

        def run(port):
            url = f"http://{HOST}:{port}/templates/{tpl}?project={urllib.parse.quote(pid)}"
            return render_preview_grid(url, out_jpg, ratio=args.ratio)

        path = _with_temp_server(run)
        print(json.dumps({"ok": True, "preview_jpg": path}, ensure_ascii=False))
        return

    if args.cmd == "render":
        pid = safe_id(args.project)
        pdir = project_path(pid)
        cfg = load_project_config(pid)
        tpl = "tvc_9x16.html" if args.ratio == "9x16" else "tvc_16x9.html"
        out_dir = os.path.join(pdir, "out")
        os.makedirs(out_dir, exist_ok=True)
        noaudio = os.path.join(out_dir, f"{pid}_{args.ratio}_noaudio.mp4")
        final_mp4 = args.out or os.path.join(out_dir, f"{pid}_{args.ratio}_{time.strftime('%Y%m%d_%H%M%S')}.mp4")

        def run(port):
            url = f"http://{HOST}:{port}/templates/{tpl}?project={urllib.parse.quote(pid)}"
            render_video(url, noaudio, ratio=args.ratio, duration=float(cfg.get("duration", 45.0)), fps=int(cfg.get("fps", 24)))
            build_and_mux_audio(pdir, cfg, noaudio, final_mp4)
            return final_mp4

        out = _with_temp_server(run)
        print(json.dumps({"ok": True, "output_mp4": out}, ensure_ascii=False))
        return

    if args.cmd == "studio":
        server = ThreadingHTTPServer((HOST, args.port), StudioHandler)
        print(f"ecom-tvc-studio running at http://{HOST}:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
