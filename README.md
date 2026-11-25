# ecom-tvc-studio

> **通用电商主图 & 短视频 AI 编导工作台（Agent Skill + 浏览器可视化预览台）** —— 支持先让 AI 吃进「参考视频」自动拉片拆解，或由 AI 从零原创脚本，自由编排任意幕数与时长的商业镜头积木，一键输出 **16:9 横屏 + 9:16 竖屏双画幅** 商用成片。

无需 Node.js，纯 Python + 浏览器即开即用，内置 **三金® 氨糖软骨素葛根胶囊** 完整可运行商业 Demo。

---

## 内置 Demo 效果示例（三金® 氨糖软骨素葛根胶囊）

**9:16 手机竖屏**

![9:16 竖屏分镜总览](examples/demo_9x16_storyboard.jpg)

**16:9 京东横屏主图**

![16:9 横屏分镜总览](examples/demo_16x9_storyboard.jpg)

---

## 核心工作流（不拘泥于单一品类或固定幕数）

1. **参考视频拉片 / AI 原创脚本**：
   - 有参考视频时：网页上传 MP4 或执行 `cli.py analyze-ref --video ref.mp4`，自动拆出 **带时间戳关键帧拉片图 + 镜头切点 + 初始 `scenes[]` 骨架 + 参考底乐**，让 AI 吃透节奏后迁移到新产品；
   - 无参考视频时：AI 直接根据产品卖点、受众与平台原创任意幕数与时长的 `scenes[]` 分镜脚本。
2. **自由分镜积木编排**：打破固定 10 幕限制，内置 7 种可自由增删组合的电商商业镜头积木（`hero_hook` 痛点钩子、`data_hud` 机理仪表盘、`split_contrast` 斜切对比、`orbit_cards` 成分环绕类比、`proof_spec` 权威背书规格、`brand_finale` 大牌落版、`custom_card` 通用卖点卡）。
3. **多品类广告法合规校验**：支持 `general`（通用电商）、`blue_hat`（蓝帽保健品）、`food`（普通/功能食品）、`skincare`（护肤美妆）四种校验模式。
4. **SRT 字幕自动拆幕对齐**：上传 `.srt` 或执行 `cli.py sync-srt`，自动按字幕时间戳同步画面分镜、配音口播与五层音效落点。
5. **逐幕中文提示词生成**：根据当前 `scenes[]` 动态生成生图与图生视频中文提示词，一键复制到外部工具生成素材。
6. **人机协同预览 & 一键出片**：浏览器打开 `http://127.0.0.1:18765`（或双击 `启动工作台.bat`），点 **`🔄 同步Agent修改`** 实时预览 `9:16 / 16:9`、增删调整分镜，确认后一键导出带 BGM + 五层音效 + `edge-tts` 自动闪避配音的 `-14/-15 LUFS` 1080p MP4。

---

## 目录结构

```text
ecom-tvc-studio/
├── SKILL.md                     # Agent Skill 入口（参考拉片 → 自由脚本 → 人机协同 6 步流程）
├── AGENTS.md                    # AI Agent 协作协议与 CLI 参考
├── agents/openai.yaml           # Codex / OpenAI Skill 元数据
├── scripts/prepare_env.py       # 一键环境自检与虚拟环境引导（输出 ENV_PY）
├── cli.py                       # Agent 原生 CLI（init / analyze-ref / check / prompts / sync-srt / preview / render）
├── app.py                       # 轻量 Web 工作台服务（纯 Python 标准库，端口 18765）
├── engine/
│   ├── ref_analyzer.py          # 参考视频智能拉片引擎（关键帧网格 + 镜头切点 + 底乐提取）
│   ├── compliance.py            # 多品类广告法合规校验（general / blue_hat / food / skincare）
│   ├── prompt_builder.py        # 基于 scenes[] 的动态中文生图 / 图生视频提示词生成器
│   ├── srt_sync.py              # SRT 字幕解析与动态分镜自动对齐引擎
│   ├── renderer.py              # Headless Edge/Chrome CDP + FFmpeg 16:9/9:16 渲染引擎
│   └── audio_mixer.py           # 三层音轨混音引擎（BGM + 动态五层音效 + edge-tts 配音闪避）
├── templates/
│   ├── dynamic_studio.html      # 通用动态分镜积木引擎（支持 16:9 & 9:16 任意幕数与时长）
│   ├── tvc_16x9.html            # 内置三金 Demo 16:9 精修模板
│   └── tvc_9x16.html            # 内置三金 Demo 9:16 精修模板
├── web/
│   └── index.html               # 可视化动态分镜编排工作台
├── examples/                    # 16:9 & 9:16 分镜效果图 + sample_sanjin.srt
└── projects/
    └── sanjin-antang/           # 内置完整商业 Demo：三金® 氨糖软骨素葛根胶囊
```

---

## 快速启动（Windows）

```powershell
python scripts/prepare_env.py
python app.py
```

启动后浏览器访问：**`http://127.0.0.1:18765`** 即可开始使用！
