---
name: ecom-tvc-studio
description: 将产品官方原图、实拍动态素材与卖点信息制作成 16:9 / 9:16 电商主图与短视频的 Agent Skill（含浏览器可视化预览台、蓝帽合规校验、中文提示词生成与三层音轨混音）。
---

# ecom-tvc-studio Skill（电商主图 & 短视频人机协同工作流）

本 Skill 用于与人类创作者协同制作 **16:9（京东/淘宝横屏主图）** 与 **9:16（抖音/手机竖屏）** 电商商拍视频（特别适用于蓝帽保健食品、功能食品与中老年大健康品类）。

核心理念：**「逐步确认、预览先行、人机协同」**——AI Agent 负责结构化配置、合规校验、提示词生成、MP4 拆帧与渲染；人类在浏览器可视化工作台（`http://127.0.0.1:18765`）随时预览、切换画幅、微调文案与音轨。

---

## 环境准备（首次运行必做）

```bash
python scripts/prepare_env.py --check
python scripts/prepare_env.py
```

成功后会输出 `ENV_PY=<解释器路径>`，后续所有命令请使用该 `<ENV_PY>` 执行。

---

## 标准 6 步工作流（每步确认后再推进，避免浪费渲染时间）

### 第 1 步：初始化项目 & 提取产品事实
1. 向用户收集：官方产品原图（盒+瓶、单瓶、Logo、蓝帽标、胶囊）、成分表/外包装文字、可选参考视频。
2. 创建项目：
   ```bash
   <ENV_PY> cli.py init --id <项目ID> --name "<产品名称>"
   ```
3. 将核实后的产品事实写入 `projects/<项目ID>/project.json`：
   - 蓝帽批号、批准功能（严格按官方原文，绝不编造治疗功效）；
   - 3 个真实痛点（中老年视角、无空洞虚词）；
   - 4 组营养成分/类比与 10 幕配音口播词；
   - 必填底部声明：`保健食品不是药物，不能代替药物治疗疾病。`
4. 运行蓝帽合规自检并向用户确认文案：
   ```bash
   <ENV_PY> cli.py check --project <项目ID>
   ```
5. （可选）如果用户提供了 `.srt` 口播字幕文件，可直接用 SRT 自动拆幕并同步 10 幕时长、口播词与五层音效落点：
   ```bash
   <ENV_PY> cli.py sync-srt --project <项目ID> --srt <口播字幕.srt>
   ```
   **⏸ 暂停等待用户确认文案与合规结果。**

### 第 2 步：输出中文提示词 & 素材入库
1. 生成全套中文生图 / 图生视频提示词包发给用户：
   ```bash
   <ENV_PY> cli.py prompts --project <项目ID>
   ```
2. **官方原图零 AI 重绘原则**：将官方原图直接放入 `projects/<项目ID>/assets/official/`（`product_combo.png`、`product_bottle.png`、`sanjin_logo.png`、`blue_hat.png`、`capsule_green.png`）。
3. 用户外部生成好 3 段 4–5 秒 16:9 实拍痛点 MP4 后，自动拆 24fps 帧入库：
   ```bash
   <ENV_PY> cli.py ingest-video --project <项目ID> --slot frames_02 --file <痛点1_上楼.mp4>
   <ENV_PY> cli.py ingest-video --project <项目ID> --slot frames_01 --file <痛点2_扶腰.mp4>
   <ENV_PY> cli.py ingest-video --project <项目ID> --slot frames_03 --file <痛点3_抽筋.mp4>
   ```
   **⏸ 暂停确认所有素材就位。**

### 第 3 步：生成 11 帧检查图（自检防翻车）
```bash
<ENV_PY> cli.py preview --project <项目ID> --ratio 9x16
<ENV_PY> cli.py preview --project <项目ID> --ratio 16x9
```
AI Agent 必须先用读图工具检查 `projects/<项目ID>/out/preview_9x16.jpg`（及 `16x9`）：
- 确认 3 段痛点视频槽位未错位、红圈精准落在痛点部位；
- 确认所有大字无压字、无单字折行、无遮挡斜切光刃；
- 确认蓝帽批号与必填合规声明清晰完整。

### 第 4 步：载入浏览器预览台，人工微调与确认
启动或指向可视化 Web 工作台（默认 `http://127.0.0.1:18765`）：
```bash
<ENV_PY> cli.py studio
```
请用户在浏览器中：
- 点击 **`🔄 同步Agent修改`** 加载最新配置；
- 一键切换 **`9:16 竖屏` / `16:9 横屏`**，拖动 `0–45s` 时间轴实时预览；
- 微调文案、替换素材或调整三层音轨开关（BGM / 五层贴画音效 / `edge-tts` 配音）。
**⏸ 等待用户在工作台或对话中确认定稿。**

### 第 5 步：全帧渲染与三层音轨合成
用户可在网页直接点击 **`▶ 一键渲染出片`**，或由 Agent 执行：
```bash
<ENV_PY> cli.py render --project <项目ID> --ratio 9x16
<ENV_PY> cli.py render --project <项目ID> --ratio 16x9
```
自动完成 1080p 24fps H.264 渲染 + 参考风 BGM 节拍无缝延展 + 5 层贴画音效 + `edge-tts` 配音自动闪避与 `-14 / -15 LUFS` 商用响度均衡。

---

## 质量红线检查清单

- [ ] 官方包装、Logo、蓝帽标全程使用原图，零 AI 重绘篡改
- [ ] `cli.py check` 零错误通过，片尾保留必填合规声明
- [ ] 三段痛点镜头各 ≥ 3.5 秒，避免跳太快看不清
- [ ] 同屏文案按 0.5–1.2 秒逐条递进，不一次性全弹出
- [ ] BGM 与五层音效/人声层次清晰，手机外放不糊不吵
