---
name: ecom-tvc-studio
description: 高定电商主图与短视频 AI 编导引擎（2.0）：面向医疗器械/蓝帽滋补、功能性食品、功效护肤与通用电商，内置像素级参考片版式拆解、+0%原速配音先行与词级毫秒对齐、分段导演级带参提示词、AI素材库严选打回、四大视觉特效与高级转场、网页有声实时联播及单镜秒级增量重渲。
---

# ecom-tvc-studio 2.0（黄金三关 · 高定电商视频生产工作流）

本引擎遵循 **「原速音频先行定轴 ➔ 导演级提示词与严选入库 ➔ 高定特效包装与单镜极速重渲」** 理念，默认**不限制视频总时长**，一律以把产品卖点讲透、`+0%` 最自然沉稳语速与舒适气口为准。

---

## 环境解释器约定

统一使用虚拟环境 Python 执行所有 CLI 命令：
```powershell
Set-Location "D:\CCJ\github\ecom-tvc-studio"
.\.venv\Scripts\python.exe cli.py --help
```

---

## 核心铁律（Agent 必须严格遵守）

1. **原速音频先行（Audio-First，严禁二次倍速赶拍）**：
   - 写完分镜口播词后，**必须在出视频提示词之前**先运行 `cli.py build-vo --project <项目ID>`；
   - 系统会以 `+0%` 标准自然播音原速生成语音，提取 `WordBoundary` 词级毫秒时间戳写入 `sub_cues / stomp_cues / focus_cues`，并根据 `真实语音时长 + 0.42s 呼吸气口` 自动反推每一镜精确秒数与建议生视频时长（`5s` 或 `10s`）。
2. **中文包装真品亮相必做动态视频（零乱码、禁偷懒）**：
   - 产品出场镜头严禁只放静态图缩放充数！默认指导用户上传 `产品事实库` 官方外盒 + 内袋/瓶身 + 内容物原图开启即梦/可灵「多图主体参考」（或先无损合成真字高清首帧再跑图生视频），确保包装文字 100% 零变形且具备流光展台大片感。
3. **分段导演级带参提示词**：
   - 每镜提示词首行必须置顶标明 **`【平台必选参数】画幅比例 ｜ 建议生成时长(5s/10s) ｜ 必传参考图清单`**，正文必须写清景别光影与分秒级动作递进（如 `【0-1.8s】...【1.8-5.0s】...`）。
4. **`AI素材库` 逐帧严选与主动打回机制**：
   - 用户将生成的视频放入 `AI素材库` 后，先运行 `cli.py audit-lib --dir "<AI素材库>" --project <项目ID>` 并用 `read_file` 逐条审片；
   - 自动挑出最自然动作段卡点，口播长于素材时用 `--loop-tail <起秒>:<止秒>` 只循环后半段停留动作（严禁整段倒放导致“倒退走路”穿帮）；
   - 若发现比例选错、动作幅度过弱、穿模或包装字糊，**必须主动指出并附优化版提示词请用户重跑**，绝不凑合。
5. **高定视觉特效与情绪分段花字**：
   - 前 3 秒痛点钩子默认启用 `pain_fx / anchor_fx`（痛点声波红圈 / 护肤瞄准框 / 活力呼吸光晕，支持动态坐标跟随）+ 差异化动效花字（`pain_q` 亮金微弹 / `pain_stomp3` 卡点砸屏微震 / `pain_urgent` 红字+激光扫光条）；
   - 产品与机理段切换为 `pro_glass` 磨砂胶囊字幕 + 关键词异色高亮，按需调用 `coverflow3`（3D 居中悬浮轮播大卡）、`pip_loupe`（显微镜画中画放大窗）、`wipe_compare`（前后激光扫描对比）；
   - 痛点间用 `whip_zoom` 微推快切，切入产品必配 `optical_flash` 暖白闪白 + Riser 唤醒重音，后半程用 `dissolve` 丝滑叠化。

---

## 标准「黄金三关」人机协作流程

### 【第一关 · 脚本、版式契约与原速定轴对齐】
1. **初始化与参考拉片（可选）**：
   ```powershell
   .\.venv\Scripts\python.exe cli.py init --id <项目ID> --name "<产品名称>" --category <medical_device|blue_hat|functional_food|skincare|general> --mode ref_frame
   .\.venv\Scripts\python.exe cli.py analyze-ref --video "<参考视频.mp4>" --project <项目ID> --extract-audio
   ```
   `analyze-ref` 会自动检测参考片属于 `three_band`（三段式包框及 `16:9`/`4:3` 视窗比例）还是 `fullscreen`（全屏沉浸式），并输出拉片图 `out/_ref/ref_storyboard.jpg` 供 Agent 读图拆解。
2. **合规校验 + 原速配音定轴 + 导演提示词生成**：
   ```powershell
   .\.venv\Scripts\python.exe cli.py check --project <项目ID>
   .\.venv\Scripts\python.exe cli.py build-vo --project <项目ID>
   .\.venv\Scripts\python.exe cli.py prompts --project <项目ID>
   ```
   **⏸ 关卡 ① 对齐**：将《分镜表（含原速精确秒数）+ 版式契约 + 分段导演级带参提示词》发给用户确认，用户据此生成视频素材。

---

### 【第二关 · 审片选段、特效实装与预览对齐】
1. **素材库全量体检与智能切帧入库**：
   ```powershell
   .\.venv\Scripts\python.exe cli.py audit-lib --dir "<AI素材库路径>" --project <项目ID>
   .\.venv\Scripts\python.exe cli.py ingest-video --project <项目ID> --slot s1_1 --file "<视频路径>" --loop-tail auto
   ```
2. **生成实装预览长图并读图自检（必做）**：
   ```powershell
   .\.venv\Scripts\python.exe cli.py preview --project <项目ID> --ratio 9x16
   ```
   Agent 必须用 `read_file` 查看预览长图，逐镜检查花字显色、人物头顶留白、痛点红圈落点、3D 轮播各阶段卡片构图无误；同时确保本地工作台 `http://127.0.0.1:18765` 在线（支持 **`🔊 有声实时联播`** 与点击画面拾取痛点坐标）。
   **⏸ 关卡 ② 对齐**：向用户展示《全镜实装高清预览长图》（或请用户直接确认出片）。

---

### 【第三关 · 分段极速重渲与双件套标准交付】
```powershell
.\.venv\Scripts\python.exe cli.py render --project <项目ID> --ratio 9x16 --out "<工作区目录>\<产品名>_成片_9x16.mp4"
```
- 渲染器默认启用 **`out/_segments/` 镜头级 SHA-1 分段缓存**：后续局部微调某一镜文案、坐标或单条素材时，仅重渲变更的那 1 镜（约 `5 秒`）并无损拼接全片！
- 渲染完成后 Agent 必须用 `read_file` 复核最终 MP4 音画气口，在用户项目工作区干净交付：
  1. **高清最终成片 MP4**
  2. **全镜实装高清预览长图 JPG**
