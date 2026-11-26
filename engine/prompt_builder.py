"""Director-Grade Segmented Chinese Prompt Builder (2.0).

Enforces the agreed 2.0 Prompt Standards:
  1. Top-pinned mandatory platform parameter header on every shot:
     【平台必选参数】画幅比例 | 建议生成时长（按+0%原速配音算准） | 必传官方参考图清单
  2. Multi-beat time-segmented director descriptions (【0-1.8s】...【1.8-3.6s】...【3.6-5.0s】)
     specifying camera framing, lighting/materials, and progressive action choreography.
  3. Product reveal (`proof_spec`) ALWAYS generates a dynamic multi-image-reference showcase
     video prompt (never lazy static-image fallback) to keep Chinese packaging 100% sharp & ungarbled.
"""

from __future__ import annotations

SCENE_TYPE_GUIDE = {
    "hero_hook": ("痛点实拍钩子", "即梦 3.0 / 可灵"),
    "proof_spec": ("真品高光动态出场（多图主体参考）", "即梦 3.0 多图参考 / 可灵多主体参考"),
    "data_hud": ("3D 超微距科研机理 CG", "即梦 3.0 / 可灵（3D 医疗科研渲染）"),
    "split_contrast": ("前后对比 / 新旧方案对照", "即梦 3.0 / 可灵"),
    "orbit_cards": ("多场景人群 / 成分矩阵（3D轮播）", "即梦 3.0 / 可灵"),
    "brand_finale": ("修护舒展与品牌温暖落版", "即梦 3.0 / 可灵"),
    "custom_card": ("卖点渗透实证特写", "即梦 3.0 / 可灵"),
}


def _infer_scene_ratio(cfg: dict, sc: dict) -> str:
    if sc.get("prompt_ratio"):
        return str(sc["prompt_ratio"])
    vp_mode = str(sc.get("vp_mode") or "")
    if vp_mode in ("coverflow3", "split3"):
        return "9:16 竖屏（共需 3 条独立竖版视频）"
    tmode = str(cfg.get("template_mode") or "dynamic")
    if tmode == "ref_frame":
        vp_r = str(cfg.get("viewport_ratio") or "16:9")
        return f"{vp_r} 横屏（嵌入三段式中间动态视窗）"
    return "9:16 竖屏（全屏沉浸式）"


def _header_banner(ratio_txt: str, sc_dur: float, rec_sec: int, ref_imgs: str) -> str:
    return (
        f"【平台必选参数】画幅比例：{ratio_txt} ｜ 建议生成时长：{rec_sec}秒（对应原速口播 {sc_dur:.1f}s）"
        f" ｜ 必传参考图：{ref_imgs}\n"
    )


def _build_dynamic_prompts(cfg: dict) -> list[dict]:
    brand = cfg.get("brand") or {}
    prod_name = brand.get("product_name") or cfg.get("project_name") or "本产品"
    cat_tag = brand.get("category_tag") or "大健康与品质消费"
    category = str(cfg.get("category") or "general").lower()
    scenes = cfg.get("scenes") or []
    packs: list[dict] = []

    for idx, sc in enumerate(scenes):
        stype = sc.get("type", "custom_card")
        vp_mode = sc.get("vp_mode", "clip")
        title = sc.get("title", f"第 {idx + 1} 幕")
        sub = sc.get("subtitle", "")
        vo = sc.get("vo_text", "")
        st = float(sc.get("start", 0.0))
        en = float(sc.get("end", st + 4.5))
        sc_dur = max(2.0, en - st)
        rec_sec = int(sc.get("rec_gen_sec") or (5 if sc_dur <= 4.8 else 10))
        ratio_txt = _infer_scene_ratio(cfg, sc)
        group, model = SCENE_TYPE_GUIDE.get(stype, SCENE_TYPE_GUIDE["custom_card"])

        if sc.get("custom_prompt_image") or sc.get("custom_prompt_video"):
            ref_hint = sc.get("ref_assets") or ("产品事实库官方外盒+内袋+实物原图" if stype == "proof_spec" else "无需传产品图（纯场景生成）")
            hdr = _header_banner(ratio_txt, sc_dur, rec_sec, ref_hint)
            packs.append({
                "id": sc.get("id", f"s{idx + 1:02d}"),
                "group": f"{group}（{sc.get('id', '')}）",
                "title": f"第 {idx + 1} 镜 · {title}（{st:.1f}–{en:.1f}s，共 {sc_dur:.1f}s）",
                "ratio": f"{ratio_txt} · 选 {rec_sec}s",
                "recommended_model": sc.get("prompt_model") or model,
                "prompt_image": hdr + str(sc.get("custom_prompt_image", "")),
                "prompt_video": hdr + str(sc.get("custom_prompt_video", "")) if sc.get("custom_prompt_video") else "",
            })
            continue

        if vp_mode in ("coverflow3", "split3"):
            items = sc.get("items") or [{"title": "场景人群1"}, {"title": "场景人群2"}, {"title": "场景人群3"}]
            hdr = _header_banner("9:16 竖屏（请分别勾选 9:16 竖屏生成 3 条）", sc_dur, 5, "无需传产品包装图")
            sub_prompts = []
            for ci, it in enumerate(items[:3]):
                it_title = it.get("title", f"适用人群{ci + 1}")
                sub_prompts.append(
                    f"▶ 卡片 0{ci + 1}《{it_title}》（9:16 竖屏 · 5秒）：\n"
                    f"  商业写实摄影，85mm 浅景深中景构图，人物头顶预留充足天空/环境呼吸空间，痛处/关注部位位于画面中偏下三分之二处（避免贴底被名牌遮挡）。"
                    f"【0-1.8s】真实中国目标受众在典型日常场景中自然活动并因「{it_title}」放慢停步；"
                    f"【1.8-5.0s】微俯身用手轻扶/揉按不适部位，面露真实克制的微表情，摄影机缓慢平稳微推聚焦，无文字、无字幕、无水印。"
                )
            p_img = hdr + "\n".join(sub_prompts)
            p_vid = hdr + "可直接复制上方每张卡片提示词在即梦/可灵勾选【9:16 竖屏 · 5秒】一段式文生视频直出。"
        elif stype == "hero_hook":
            hdr = _header_banner(ratio_txt, sc_dur, rec_sec, "无需传产品包装图")
            p_img = hdr + (
                f"商业写实电影摄影首帧，35mm 镜头浅景深，主题：{cat_tag}。"
                f"自然通透的真实居家/生活光线，一位真实中国受众正经历「{title}」（{sub}），手部自然扶按对应部位，神情真实克制不浮夸，背景柔和虚化，无任何文字、无产品盒、无水印。"
            )
            p_vid = hdr + (
                f"真实电影级商拍广告镜头，{rec_sec}秒。\n"
                f"【0-1.6s】人物在自然生活场景中准备起身或迈步，因「{sub or title}」动作出现真实停顿迟疑；\n"
                f"【1.6-{rec_sec}.0s】双手自然扶住并轻揉不适部位，眉头微蹙轻轻叹气，摄影机沿痛点方向平稳缓慢微推，光影柔和高级，无字幕、无水印。"
            )
        elif stype == "proof_spec":
            hdr = _header_banner(ratio_txt, sc_dur, rec_sec, "必传【官方外盒正斜视图 + 内袋/瓶身图 + 膏体/内容物实拍图】开启多主体参考")
            tone = "冰蓝与纯白渐变科技光学玻璃展台" if category in ("medical_device", "blue_hat") else (
                "温润香槟金与高透亚克力水波纹高奢展台" if category == "skincare" else "清晨阳光通透的原木与浅米洞石自然展台"
            )
            p_img = hdr + (
                f"高端商业广告产品静物大片，{tone}。画面黄金三角层次陈列参考图中的「{prod_name}」官方外盒、独立内包装与真实内容物主体，"
                f"严格保持参考图包装上的品牌标志与全部中文排版 100% 清晰锐利零变形，细腻轮廓棚拍光与通透倒影，浅景深商业质感，无杂物无水印。"
            )
            p_vid = hdr + (
                f"高端 TVC 产品高光出场镜头，{rec_sec}秒（建议选 60fps 高帧率模式）。\n"
                f"【0-1.8s】明亮通透的{tone}上，「{prod_name}」外盒稳立左后方，内袋与产品本体在前景呈立体层次优雅微浮展开；\n"
                f"【1.8-{rec_sec}.0s】一道柔和纯净的暖金与冰蓝丝绸流光从左向右缓缓掠过盒面与产品肌理，空气中漂浮极细腻微光粒子，摄影机以微距轨道平稳缓慢推进并轻微环绕，全程保持包装中文清晰稳定不变形，无字幕无水印。"
            )
        elif stype == "data_hud":
            hdr = _header_banner(ratio_txt, sc_dur, rec_sec, "无需传包装图（纯 3D 微距科研渲染）")
            p_img = hdr + (
                f"C4D Octane 渲染器级别 3D 超微距科研剖面大片，冰蓝与暖金交织光学质感。35 度斜俯超微距视角，"
                f"立体分层拆解展示「{title}」（{sub}）的精密微观结构与晶莹活性阵列，上方悬浮发光能量核心释放纳米级微粒，近景锐利远景虚化，无任何文字、无数字、无水印。"
            )
            p_vid = hdr + (
                f"高端广告级 3D 超微距 CG 动画，{rec_sec}秒，细节饱满递进：\n"
                f"【0-1.8s】画面上方晶莹能量核心柔和脉动，释放细腻闪烁的暖金色活性微粒如星云般渗入下方多层微观结构；\n"
                f"【1.8-3.6s】摄影机以超微距低角度贴近微观阵列平稳向前滑行推进，底层亮起温暖呼吸光波，洁白透气丝流从微孔间轻盈升腾逸出；\n"
                f"【3.6-{rec_sec}.0s】整片微观结构随柔韧基底轻微起伏舒展，表面泛起温润光学折射涟漪，运镜丝滑连贯，全程无文字无水印。"
            )
        else:
            hdr = _header_banner(ratio_txt, sc_dur, rec_sec, "按需参考产品内容物图")
            p_img = hdr + (
                f"高端三维可视化/商业实拍大片，明亮纯净柔光背景。围绕「{title}」（{sub or vo}）直观展现修护渗透与舒缓后的轻松健康状态，光影干净通透，无血腥恐怖感，无文字无水印。"
            )
            p_vid = hdr + (
                f"高端商业广告动态镜头，{rec_sec}秒。\n"
                f"【0-2.0s】温润暖金能量流持续深入目标部位，紧绷泛红感柔和消退；\n"
                f"【2.0-{rec_sec}.0s】主体恢复洁白温润的舒展活力状态，动作自然顺畅轻盈，摄影机缓慢平稳推进，无字幕无水印。"
            )

        packs.append({
            "id": sc.get("id", f"s{idx + 1:02d}"),
            "group": f"{group}（{sc.get('id', '')}）",
            "title": f"第 {idx + 1} 镜 · {title}（{st:.1f}–{en:.1f}s，共 {sc_dur:.1f}s）",
            "ratio": f"{ratio_txt} · 选 {rec_sec}s",
            "recommended_model": model,
            "prompt_image": p_img,
            "prompt_video": p_vid,
        })

    return packs


def build_prompt_pack(cfg: dict) -> list[dict]:
    if cfg.get("template_mode") in ("dynamic", "ref_frame") or cfg.get("scenes"):
        return _build_dynamic_prompts(cfg)
    return _build_dynamic_prompts(cfg)
