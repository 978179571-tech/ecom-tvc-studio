---
name: ecom-tvc-studio
description: Collaborate with the human creator using ecom-tvc-studio (CLI + Visual Web Studio) to produce 16:9 and 9:16 e-commerce health-supplement/product videos from official packaging photos, verified facts, live-action pain MP4s, and 3-layer audio.
---

# ecom-tvc-studio Agent Skill

Use this skill whenever the user wants to create or iterate on an e-commerce product video (16:9 JD main-image or 9:16 Douyin/mobile vertical) inside `ecom-tvc-studio`.

## Standard Workflow

1. **Initialize project**:
   ```bash
   python cli.py init --id <project_id> --name "<Product Name>"
   ```
2. **Populate `projects/<project_id>/project.json`**:
   - Extract verified brand name, approval number (`国食健注...`), approved functions, dosage, 3 real-life pain points, 4 nutrient cards, and 10 scene voiceover lines.
   - Never fabricate efficacy claims or alter official packaging text.
3. **Verify compliance**:
   ```bash
   python cli.py check --project <project_id>
   ```
   Fix all reported errors before proceeding.
4. **Generate Chinese prompts & ingest assets**:
   - Run `python cli.py prompts --project <project_id>` to give the user ready-to-copy Chinese prompts for live-action pain videos and macro ingredients.
   - Place official untouched assets in `projects/<project_id>/assets/official/`.
   - When the user provides pain-point MP4 clips, extract 24fps frames:
     ```bash
     python cli.py ingest-video --project <project_id> --slot frames_02 --file <pain1.mp4>
     python cli.py ingest-video --project <project_id> --slot frames_01 --file <pain2.mp4>
     python cli.py ingest-video --project <project_id> --slot frames_03 --file <pain3.mp4>
     ```
5. **Preview & Human-in-the-Loop Review**:
   - Run `python cli.py preview --project <project_id> --ratio 9x16` and visually inspect the generated `out/preview_9x16.jpg`.
   - Start or point the user to the Visual Web Studio (`http://127.0.0.1:18765`) so they can scrub the timeline, tweak text/audio toggles, or switch `16:9` / `9:16`.
6. **Final Render**:
   ```bash
   python cli.py render --project <project_id> --ratio 9x16
   ```
   (Or let the user trigger **▶ 一键渲染出片** directly in the Web Studio.)
