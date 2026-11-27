"""Agent-Native CLI for ecom-tvc-studio 2.0."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import time
from http.server import ThreadingHTTPServer

from app import (
    HOST, PORT, StudioHandler, create_project_dir, list_projects,
    load_project_config, project_path, resolve_template_file,
    resolve_template_rel, safe_id, save_project_config,
)
from engine.audio_mixer import build_and_mux_audio, build_preview_audio_wav, build_vo_timeline
from engine.compliance import check_compliance
from engine.prompt_builder import build_prompt_pack
from engine.ref_analyzer import analyze_reference_video
from engine.renderer import (
    audit_ai_library,
    extract_video_frames,
    render_preview_grid,
    render_video_segmented,
)
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
    parser = argparse.ArgumentParser(prog="ecom-tvc-studio", description="ecom-tvc-studio 2.0 Agent-Native CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all projects")

    p_init = sub.add_parser("init", help="Create a new project (2.0 ref_frame/dynamic mode)")
    p_init.add_argument("--id", required=True)
    p_init.add_argument("--name", required=True)
    p_init.add_argument(
        "--category",
        default="medical_device",
        choices=["medical_device", "blue_hat", "food", "functional_food", "skincare", "general"],
    )
    p_init.add_argument("--mode", default="ref_frame", choices=["ref_frame", "dynamic", "sanjin_demo"])

    p_ref = sub.add_parser("analyze-ref", help="Deconstruct a reference MP4 into storyboard, frame contract & starter scenes")
    p_ref.add_argument("--video", required=True, help="Path to reference MP4 video")
    p_ref.add_argument("--project", default="", help="Optional project ID to apply the extracted scene skeleton into")
    p_ref.add_argument("--extract-audio", action="store_true", help="Also extract reference audio to audio/bgm_ref.wav")

    p_vo = sub.add_parser("build-vo", help="Audio-First: synthesize +0% natural VO, extract WordBoundary cues & set scene timings")
    p_vo.add_argument("--project", required=True)
    p_vo.add_argument("--voice", default="", help="Optional edge-tts voice override")
    p_vo.add_argument("--rate", default="+0%", help="Speech rate (default +0% natural broadcast speed)")
    p_vo.add_argument("--breath", type=float, default=0.42, help="Natural breath gap between scenes in seconds")

    p_chk = sub.add_parser("check", help="Run multi-category advertising law compliance check")
    p_chk.add_argument("--project", required=True)

    p_pr = sub.add_parser("prompts", help="Generate segmented director-grade Chinese image & video prompts")
    p_pr.add_argument("--project", required=True)

    p_aud = sub.add_parser("audit-lib", help="Audit all generated videos in AI素材库 and build visual QA sheet")
    p_aud.add_argument("--dir", required=True, help="Path to AI素材库 directory")
    p_aud.add_argument("--project", default="", help="Optional project ID to save audit_sheet.jpg under out/")

    p_iv = sub.add_parser("ingest-video", help="Extract 24fps frames from an MP4 with optional trim & ping-pong tail loop")
    p_iv.add_argument("--project", required=True)
    p_iv.add_argument("--slot", required=True, help="Clip slot id like s1_1, s2_1, s3, s4_1")
    p_iv.add_argument("--file", required=True)
    p_iv.add_argument("--width", type=int, default=1280)
    p_iv.add_argument("--height", type=int, default=720)
    p_iv.add_argument("--trim-start", type=float, default=0.0)
    p_iv.add_argument("--trim-dur", type=float, default=0.0)
    p_iv.add_argument("--loop-tail", default="auto", help="auto | none | start_sec:end_sec (e.g. 3.4:5.9)")
    p_iv.add_argument("--target-dur", type=float, default=0.0, help="Target scene duration in seconds")

    p_srt = sub.add_parser("sync-srt", help="Parse an .srt file and auto-align scenes, duration & VO lines")
    p_srt.add_argument("--project", required=True)
    p_srt.add_argument("--srt", required=True, help="Path to .srt subtitle file")

    p_rst = sub.add_parser("reset-timing", help="Reset custom SRT scene timings")
    p_rst.add_argument("--project", required=True)

    p_pv = sub.add_parser("preview", help="Render keyframe contact sheet preview")
    p_pv.add_argument("--project", required=True)
    p_pv.add_argument("--ratio", default="9x16", choices=["9x16", "16x9"])

    p_rd = sub.add_parser("render", help="Incremental segment-cached MP4 render + 3-layer audio mix")
    p_rd.add_argument("--project", required=True)
    p_rd.add_argument("--ratio", default="9x16", choices=["9x16", "16x9"])
    p_rd.add_argument("--out", default="", help="Optional custom output MP4 path")
    p_rd.add_argument("--full", action="store_true", help="Force full re-render ignoring segment cache")

    p_st = sub.add_parser("studio", help="Launch Visual Web Studio 2.0 (with live audio sync & coord picker)")
    p_st.add_argument("--port", type=int, default=PORT)

    args = parser.parse_args()

    if args.cmd == "list":
        print(json.dumps({"projects": list_projects()}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "init":
        pid = safe_id(args.id)
        try:
            create_project_dir(pid, args.name, category=args.category, mode=args.mode)
        except ValueError as exc:
            raise SystemExit(str(exc))
        print(json.dumps({
            "ok": True,
            "project_id": pid,
            "mode": args.mode,
            "category": args.category,
            "config_path": os.path.join(project_path(pid), "project.json"),
        }, ensure_ascii=False, indent=2))
        return

    if args.cmd == "analyze-ref":
        if args.project:
            pid = safe_id(args.project)
            pdir = project_path(pid)
            out_dir = os.path.join(pdir, "out", "_ref")
            bgm_dst = os.path.join(out_dir, "ref_audio.wav") if args.extract_audio else None
            res = analyze_reference_video(args.video, out_dir, extract_audio_path=bgm_dst)
            cfg = load_project_config(pid)
            lc = res.get("layout_contract") or {}
            cfg["template_mode"] = "ref_frame"
            cfg["layout_mode"] = "three_band" if lc.get("is_three_band_frame") else "fullscreen"
            if lc.get("is_three_band_frame"):
                cfg["viewport_ratio"] = lc.get("recommended_1080x1920_contract", {}).get("viewport_ratio", "16:9")
            cfg["duration"] = res["meta"]["duration"]
            cfg["scenes"] = res["suggested_scenes"]
            save_project_config(pid, cfg)
            print(json.dumps({"ok": True, "project_id": pid, **res}, ensure_ascii=False, indent=2))
        else:
            out_dir = os.path.join(os.path.dirname(os.path.abspath(args.video)), "_ref_analysis")
            bgm_dst = os.path.join(out_dir, "bgm_ref.wav") if args.extract_audio else None
            res = analyze_reference_video(args.video, out_dir, extract_audio_path=bgm_dst)
            print(json.dumps({"ok": True, **res}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "build-vo":
        pid = safe_id(args.project)
        pdir = project_path(pid)
        cfg = load_project_config(pid)
        report = build_vo_timeline(pdir, cfg, voice_override=args.voice, rate=args.rate, breath_gap=args.breath)
        save_project_config(pid, cfg)
        wav_path = build_preview_audio_wav(pdir, cfg)
        print(json.dumps({"ok": True, "project_id": pid, "preview_wav": wav_path, **report}, ensure_ascii=False, indent=2))
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

    if args.cmd == "audit-lib":
        sheet_out = None
        if args.project:
            sheet_out = os.path.join(project_path(safe_id(args.project)), "out", "ai_lib_audit.jpg")
        else:
            sheet_out = os.path.join(os.path.abspath(args.dir), "_ai_lib_audit.jpg")
        res = audit_ai_library(args.dir, out_sheet_jpg=sheet_out)
        print(json.dumps({"ok": True, **res}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "ingest-video":
        pid = safe_id(args.project)
        pdir = project_path(pid)
        cfg = load_project_config(pid)
        lt = None if args.loop_tail.lower() == "none" else args.loop_tail
        tdur = args.target_dur
        sc_match = next((s for s in (cfg.get("scenes") or []) if (s.get("frame_slot") or s.get("id")) == args.slot), None)
        if tdur <= 0 and sc_match:
            tdur = float(sc_match.get("end", 4.0)) - float(sc_match.get("start", 0.0)) + 0.35

        if args.slot in ("frames_01", "frames_02", "frames_03") and cfg.get("template_mode") != "ref_frame":
            cnt = extract_video_frames(args.file, os.path.join(pdir, "assets", "v5", args.slot), width=1920, height=1080)
        else:
            cnt = extract_video_frames(
                args.file,
                os.path.join(pdir, "assets", "clips", args.slot),
                width=args.width,
                height=args.height,
                trim_start=args.trim_start,
                trim_dur=(args.trim_dur if args.trim_dur > 0 else None),
                loop_tail=lt,
                target_dur=tdur,
            )
            if sc_match is not None:
                sc_match["clip_frames"] = cnt
                save_project_config(pid, cfg)
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
        cfg = load_project_config(pid)
        out_jpg = os.path.join(project_path(pid), "out", f"preview_{args.ratio}.jpg")

        def run(port):
            url = f"http://{HOST}:{port}{resolve_template_rel(pid, cfg, args.ratio)}"
            return render_preview_grid(url, out_jpg, ratio=args.ratio, scenes=cfg.get("scenes"))

        path = _with_temp_server(run)
        print(json.dumps({"ok": True, "preview_jpg": path}, ensure_ascii=False))
        return

    if args.cmd == "render":
        pid = safe_id(args.project)
        pdir = project_path(pid)
        cfg = load_project_config(pid)
        out_dir = os.path.join(pdir, "out")
        os.makedirs(out_dir, exist_ok=True)
        noaudio = os.path.join(out_dir, f"{pid}_{args.ratio}_noaudio.mp4")
        final_mp4 = args.out or os.path.join(out_dir, f"{pid}_{args.ratio}_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
        tpl_file = resolve_template_file(cfg, args.ratio)

        def run(port):
            url = f"http://{HOST}:{port}{resolve_template_rel(pid, cfg, args.ratio)}"
            seg_stat = render_video_segmented(
                project_dir=pdir,
                tpl_file=tpl_file,
                cfg=cfg,
                scene_url=url,
                out_mp4=noaudio,
                ratio=args.ratio,
                fps=int(cfg.get("fps", 24)),
                force_full=args.full,
            )
            build_and_mux_audio(pdir, cfg, noaudio, final_mp4)
            shutil.copyfile(final_mp4, os.path.join(out_dir, f"{pid}_{args.ratio}_latest.mp4"))
            return final_mp4, seg_stat

        out, seg_stat = _with_temp_server(run)
        print(json.dumps({"ok": True, "output_mp4": out, **seg_stat}, ensure_ascii=False))
        return

    if args.cmd == "studio":
        server = ThreadingHTTPServer((HOST, args.port), StudioHandler)
        print(f"ecom-tvc-studio 2.0 running at http://{HOST}:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
