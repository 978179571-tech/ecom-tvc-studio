# ecom-tvc-studio Skill

> **搭配 AI Agent + 浏览器可视化预览台的电商主图/短视频制作 Skill** —— 采用「逐步确认、预览先行、人机协同」工作流，专为保健品（蓝帽）、功能食品、大健康品类打造 **16:9 横屏 + 9:16 竖屏双画幅** 一键复用生产线。

无需 Node.js，纯 Python + 浏览器即开即用，内置 **三金® GOP®氨糖软骨素葛根胶囊** 完整可运行 Demo。

---

## 效果示例（内置 Demo：三金® 氨糖软骨素葛根胶囊）

**9:16 手机竖屏（大字醒目 + 逐条递进节奏 + 五层音效 + 配音闪避）**

![9:16 竖屏分镜总览](examples/demo_9x16_storyboard.jpg)

**16:9 京东横屏主图**

![16:9 横屏分镜总览](examples/demo_16x9_storyboard.jpg)

---

## 工作方式（AI Agent + 浏览器工作台人机协同闭环）

1. **环境检查**：`python scripts/prepare_env.py --check`（自动输出 `ENV_PY=<路径>`）；
2. **AI Agent 建项与合规锁死**：把新品包装图与资料交给 AI Agent（如 Antigravity / Codex / Claude Code），Agent 调用 `cli.py init` 写入 `project.json` 并跑 `cli.py check` 拦截违禁医疗词；
3. **提示词与素材就位**：Agent 跑 `cli.py prompts` 输出中文提示词，拿到外部生成的 3 段动态痛点 MP4 后用 `cli.py ingest-video` 自动拆 24fps 帧；
4. **11 帧预览图自检**：Agent 跑 `cli.py preview` 先检查无压字、无折行、无素材错位；
5. **浏览器工作台人工微调**：打开 `http://127.0.0.1:18765`（或双击 `启动工作台.bat`），点 **`🔄 同步Agent修改`**，一键切换 `9:16` / `16:9`、拖时间轴预览、改文案与音轨开关；
6. **一键渲染导出**：网页点 **`▶ 一键渲染出片`** 或 Agent 跑 `cli.py render`，自动输出 `-14/-15 LUFS` 成品 MP4。

---

## 核心特性

- **可视化 Web 工作台**（`http://127.0.0.1:18765`）：左侧表单改文案、右侧实时拖动时间轴所见即所得预览；
- **SRT 字幕驱动自动拆幕对齐**：支持在工作台上传 `.srt` 或执行 `cli.py sync-srt`，自动按字幕时间戳映射 10 幕画面节奏、更新配音口播词并同步五层贴画音效落点（内置示例 [`examples/sample_sanjin.srt`](examples/sample_sanjin.srt)）；
- **16:9 横屏 / 9:16 竖屏一键切换**：原生双画幅独立排版（非黑边裁切），针对中老年人群优化超大字号与逐条递进阅读节奏；
- **一键中文提示词生成**：根据产品表单自动生成痛点实拍首帧、图生视频、暖阳桌面与食材静物中文提示词，一键复制到外部 AI 工具生图/生视频；
- **真动态 MP4 自动抽帧**：网页上传 3 段痛点实拍 MP4 后，后端自动用 FFmpeg 拆成 24fps 高清帧序列无缝嵌入；
- **11 帧分镜预览图自检**：10 秒快速出关键帧总览，提前拦截压字、折行与素材错位；
- **三层商用音轨自动化**：参考风 BGM 节拍无缝延展 + 5 层贴画细节音效 + `edge-tts` 人声配音自动闪避，统一 `-14 / -15 LUFS` 商用响度；
- **蓝帽合规词实时校验**：自动检测违禁医疗/绝对化宣传词与法规必填声明。

---

## 目录结构

```text
ecom-tvc-studio/
├── SKILL.md                 # Agent Skill 入口说明书（6 步门禁确认工作流）
├── AGENTS.md                # AI Agent 协作协议与 CLI 参考
├── agents/openai.yaml       # Codex / OpenAI Skill 元数据
├── scripts/prepare_env.py   # 一键环境自检与虚拟环境引导脚本（输出 ENV_PY）
├── cli.py                   # Agent 原生 CLI（init / check / prompts / sync-srt / preview / render）
├── app.py                   # 轻量 Web 工作台服务（纯 Python 标准库，端口 18765）
├── requirements.txt         # Python 依赖
├── engine/
│   ├── compliance.py        # 蓝帽保健品合规词校验
│   ├── prompt_builder.py    # 中文生图 / 图生视频提示词自动生成器
│   ├── srt_sync.py          # SRT 字幕解析与 10 幕自动拆幕时间轴映射引擎
│   ├── renderer.py          # Headless Edge/Chrome CDP + FFmpeg 16:9/9:16 渲染引擎
│   └── audio_mixer.py       # 三层音轨混音引擎（BGM + 5层音效 + edge-tts 配音闪避）
├── templates/
│   ├── tvc_16x9.html        # 数据驱动 16:9 横屏模板（支持 SRT 动态时间轴重映射）
│   └── tvc_9x16.html        # 数据驱动 9:16 竖屏模板（大字醒目 + 逐条递进）
├── web/
│   └── index.html           # 可视化 Web 工作台前端
├── examples/                # 16:9 & 9:16 分镜效果图 + sample_sanjin.srt
└── projects/
    └── sanjin-antang/       # 内置完整 Demo：三金® 氨糖软骨素葛根胶囊
```

---

## 快速启动（Windows）

### 1. 环境要求
- Python 3.10+
- `ffmpeg` 已加入系统 PATH
- 已安装 Microsoft Edge 或 Google Chrome

### 2. 安装依赖并启动
```powershell
pip install -r requirements.txt
python app.py
```

启动后浏览器访问：**`http://127.0.0.1:18765`** 即可开始使用！

---

## 复用制作新产品的 5 个步骤

1. 点击顶部 **`+ 新建产品`**，克隆出一份独立项目目录；
2. 在 **`📝 文案与合规`** 填写新产品的品牌、批号、痛点与核心成分，确认顶部显示 **`✓ 蓝帽合规通过`**；
3. 切到 **`✨ 中文提示词`** 一键复制提示词去外部工具（如即梦 / 可灵 / Seedance / GPT Image）生成实拍图与动态视频；
4. 在 **`🖼️ 素材上传`** 替换官方包装原图、AI 静物与 3 段痛点 MP4；
5. 切换 **`9:16 竖屏`** 或 **`16:9 横屏`**，点 **`11帧预览图`** 自检通过后，点 **`▶ 一键渲染出片`** 即可下载成品 MP4。
