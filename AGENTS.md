# AGENTS.md — AI Agent & Human-in-the-Loop Collaboration Guide

This repository (`ecom-tvc-studio`) is designed to be operated **jointly by an AI Agent (Antigravity / Claude Code / Codex / Cursor) and a Human Creator** via the Visual Web Studio (`http://127.0.0.1:18765`).

## Core Division of Labor

| Stage | AI Agent Owns (via CLI & Files) | Human Owns (via Web Studio) |
| :--- | :--- | :--- |
| **1. Init & Facts** | Read official packaging photos / brief → `python cli.py init` → populate `projects/<id>/project.json` | Confirm product facts, pain points & analogy口径 |
| **2. Compliance** | Run `python cli.py check --project <id>` to block medical/absolute claims & verify mandatory disclaimer | Review any compliance warnings |
| **3. Prompts & Assets** | Run `python cli.py prompts --project <id>` → give user Chinese prompts or place official packaging & AI assets; run `python cli.py ingest-video` on uploaded MP4s | Generate/upload real live-action pain MP4s or swap official photos |
| **4. Visual Review** | Run `python cli.py preview --project <id> --ratio 9x16` & inspect `preview_9x16.jpg` for clipping/overlap | Open `http://127.0.0.1:18765`, scrub `0–45s` timeline, switch `9:16` / `16:9`, tweak copy or audio toggles |
| **5. Final Render** | Run `python cli.py render --project <id> --ratio 9x16` (or let human click **一键渲染出片** in Web Studio) | Watch inline MP4 & download final deliverable |

## Non-Negotiable Rules for AI Agents

1. **NEVER alter official product packaging / Logo / Blue-Hat badge** with AI image generation — always copy untouched official files into `projects/<id>/assets/official/`.
2. **ALWAYS run `python cli.py check --project <id>`** before rendering any health supplement video.
3. **ALWAYS run `python cli.py preview` and visually inspect the contact sheet** before running full 1080p `render`.
4. **Live-Action Video Slot Mapping** (`projects/<id>/assets/v5/`):
   - `frames_02/` → **S1** (Pain Point 1, e.g. stairs knee pain)
   - `frames_01/` → **S2A** (Pain Point 2, e.g. lower back pain)
   - `frames_03/` → **S2B** (Pain Point 3, e.g. night leg cramp)
5. **Human-in-the-Loop Sync**: After updating `projects/<id>/project.json` on disk, remind the human to click **`🔄 同步Agent修改`** in the Web Studio topbar to see changes immediately on the live canvas.
