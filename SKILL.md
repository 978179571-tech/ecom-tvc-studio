---
name: ecom-tvc-studio
description: 通用电商主图与短视频 AI 编导 Skill：支持先用参考视频智能拉片或由 AI 原创分镜脚本，自由编排任意幕数与时长的商业镜头积木，结合多品类广告法合规校验、SRT 字幕对齐、浏览器可视化预览台与三层音轨渲染输出 16:9 / 9:16 成片。
---

# ecom-tvc-studio Skill（通用电商主图 & 短视频 AI 编导工作流）

本 Skill 面向**全品类电商主图（16:9 横屏）与短视频（9:16 竖屏）**制作，不拘泥于固定幕数或单一品类，核心理念为 **「参考拉片 / 原创脚本先行 → 逐步确认 → 预览先行 → 人机协同」**。

---

## 环境准备（首次运行必做）

```bash
python scripts/prepare_env.py --check
python scripts/prepare_env.py
```

成功后会输出 `ENV_PY=<解释器路径>`，后续所有命令请使用该 `<ENV_PY>` 执行。

---

## 标准 6 步通用编导流程（每步确认后再推进）

### 第 1 步：吃进参考视频（可选）& 原创分镜脚本设计
1. 向用户收集：**产品信息/官方原图** + **目标品类**（`general` / `blue_hat` / `food` / `skincare`）+ **可选参考视频 MP4**。
2. 初始化通用自由分镜项目：
   ```bash
   <ENV_PY> cli.py init --id <项目ID> --name "<产品名称>" --category <品类模式>
   ```
3. **如果用户提供了参考视频**：运行参考视频智能拉片工具，自动提取关键帧拉片总览图、镜头切点时间戳、参考音轨和初始分镜骨架：
   ```bash
   <ENV_PY> cli.py analyze-ref --video <参考视频.mp4> --project <项目ID> --extract-audio
   ```
   AI Agent 必须先用读图工具查看 `projects/<项目ID>/out/_ref/ref_storyboard.jpg`，吃透参考片的节奏、情绪曲线与镜头切换逻辑，再将其迁移为新产品的专属分镜脚本。
4. **如果无参考视频**：AI 直接根据产品卖点、受众与平台节奏，原创设计任意幕数与时长的 `scenes[]` 脚本，写入 `projects/<项目ID>/project.json`。
   - 可用 7 种通用商业镜头积木：`hero_hook`（痛点钩子）、`data_hud`（机理数据仪表盘）、`split_contrast`（斜切方案对比）、`orbit_cards`（核心成分/卖点环绕类比）、`proof_spec`（权威背书与规格）、`brand_finale`（品牌实景落版）、`custom_card`（通用卖点冲击卡）。
5. 运行多品类广告法合规校验：
   ```bash
   <ENV_PY> cli.py check --project <项目ID>
   ```
6. （可选）若用户提供了 `.srt` 口播字幕，可直接按字幕自动拆幕对齐画面、配音与音效：
   ```bash
   <ENV_PY> cli.py sync-srt --project <项目ID> --srt <口播字幕.srt>
   ```
   **⏸ 暂停把分镜脚本与合规校验结果发给用户确认。**

### 第 2 步：输出逐幕中文提示词 & 素材入库
1. 根据确认后的 `scenes[]` 自动生成逐幕中文生图 / 图生视频提示词包：
   ```bash
   <ENV_PY> cli.py prompts --project <项目ID>
   ```
2. **官方原图零 AI 重绘原则**：产品包装、Logo、蓝帽/认证标直接使用官方高清原图，放入 `projects/<项目ID>/assets/official/`。
3. 外部生成的静图或动态 MP4 写入各幕的 `media` 路径（动态痛点 MP4 可用 `cli.py ingest-video` 自动拆 24fps 帧）。
   **⏸ 暂停确认所有视觉素材就位。**

### 第 3 步：生成分镜关键帧检查图（自检防翻车）
```bash
<ENV_PY> cli.py preview --project <项目ID> --ratio 9x16
<ENV_PY> cli.py preview --project <项目ID> --ratio 16x9
```
AI Agent 用读图工具检查 `projects/<项目ID>/out/preview_*.jpg`，确认无压字、无遮挡、无错位、品类合规声明完整。

### 第 4 步：浏览器可视化工作台微调与定稿
启动或指向本地工作台（`http://127.0.0.1:18765`）：
```bash
<ENV_PY> cli.py studio
```
人类创作者在浏览器中：
- 点击 **`🔄 同步Agent修改`** 加载最新分镜；
- 自由增删幕次、调整每幕起止秒数与镜头积木类型、修改文案/口播词，或直接上传参考视频 / SRT；
- 一键切换 **`9:16 竖屏` / `16:9 横屏`** 实时拖动预览。
**⏸ 等待用户确认定稿。**

### 第 5 步：全帧渲染与三层商用音轨合成
用户可在网页点击 **`▶ 一键渲染出片`**，或由 Agent 执行：
```bash
<ENV_PY> cli.py render --project <项目ID> --ratio 9x16
<ENV_PY> cli.py render --project <项目ID> --ratio 16x9
```
自动完成 1080p 24fps H.264 渲染 + 参考风 BGM 节拍延展 + 动态贴画五层音效 + `edge-tts` 配音自动闪避与 `-14 / -15 LUFS` 商用响度输出。
