"""Generate ready-to-copy Chinese image & image-to-video prompts from project.json.

Supports BOTH:
  - Universal dynamic scenes[] mode (generates tailored prompts per scene block & category)
  - Legacy sanjin-antang demo mode
"""

from __future__ import annotations

SCENE_TYPE_GUIDE = {
    "hero_hook": ("痛点实拍首帧 + 图生视频", "16:9", "可灵 / 即梦 / Seedance / Gemini"),
    "data_hud": ("科学机理 / 透视视觉图", "1:1 / 16:9", "GPT Image / Gemini / 即梦"),
    "split_contrast": ("对照方案静物图（无标纯色）", "1:1", "GPT Image / 即梦"),
    "orbit_cards": ("核心成分 / 卖点主体与类比静物", "1:1", "GPT Image / 即梦"),
    "proof_spec": ("官方权威背书与产品规格特写", "原图优先", "使用官方原图（零 AI 重绘）"),
    "brand_finale": ("暖阳实景大牌桌面背景", "16:9", "GPT Image / Midjourney / 即梦"),
    "custom_card": ("通用高质感商业场景配图", "16:9", "Gemini / 即梦 / Midjourney"),
}


def _build_dynamic_prompts(cfg: dict) -> list[dict]:
    brand = cfg.get("brand") or {}
    prod_name = brand.get("product_name") or cfg.get("project_name") or "本产品"
    cat_tag = brand.get("category_tag") or "电商商业短视频"
    scenes = cfg.get("scenes") or []
    packs: list[dict] = []

    for idx, sc in enumerate(scenes):
        stype = sc.get("type", "custom_card")
        title = sc.get("title", f"第 {idx + 1} 幕")
        sub = sc.get("subtitle", "")
        badge = sc.get("badge", "")
        vo = sc.get("vo_text", "")
        group, ratio, model = SCENE_TYPE_GUIDE.get(stype, SCENE_TYPE_GUIDE["custom_card"])

        if stype == "hero_hook":
            p_img = (
                f"16:9 宽银幕 35mm 电影商业摄影质感，主题：{cat_tag}。"
                f"真实中国消费人群生活实景，画面直观传达「{title}」（{sub}）。"
                f"自然柔和窗光，浅景深电影虚化，真实情绪克制不夸张，无文字、无 Logo、无水印。"
            )
            p_vid = (
                f"真实 35mm 电影商拍质感，{max(3, round(float(sc.get('end', 4)) - float(sc.get('start', 0))))} 秒 16:9。"
                f"延续首帧人物与光线，自然呈现「{title}」的真实动作与情绪微表情，"
                f"镜头缓慢平稳微推，无字幕、无水印。"
            )
        elif stype == "data_hud":
            p_img = (
                f"高端医学/科研级极简商业可视化摄影，深蓝青或深墨绿科技质感背景。"
                f"围绕「{title}」（{sub}）呈现清晰通透的核心机理/结构透视视觉主体，柔和边缘发光，"
                f"主体居中留出上下排版安全区，无任何文字、无数字、无水印。"
            )
            p_vid = ""
        elif stype == "split_contrast":
            p_img = (
                f"极简商业棚拍静物，1:1 方图纯白或浅灰背景。呈现无任何品牌文字与图案的纯白/素色对照单品，"
                f"用于与「{prod_name}」做对比（痛点归因：{title} / {sub}）。柔和漫反射棚拍光，无文字无水印。"
            )
            p_vid = ""
        elif stype == "orbit_cards":
            items_txt = "、".join([str(it.get("title") or it) for it in (sc.get("items") or []) if it])
            p_img = (
                f"高端商业杂志微距棚拍摄影，1:1 方图纯白底（#FFFFFF），风格统一。"
                f"围绕「{title}」（{items_txt or sub}）拍摄洁净通透的核心成分/天然原料静物，"
                f"主体居中占画幅 65%–70%，柔和暖白棚拍光，无地面重阴影、无文字、无水印。"
            )
            p_vid = ""
        elif stype == "proof_spec":
            p_img = (
                f"【官方原图规范】本幕「{title}」请直接使用「{prod_name}」官方高清原图（产品瓶/盒、品牌 Logo、认证标识或检测报告原图），"
                f"切勿使用 AI 重绘包装文字，确保 100% 真实合规。"
            )
            p_vid = ""
        elif stype == "brand_finale":
            p_img = (
                f"真实高端商业广告实景背景摄影，16:9 横屏。明亮通透的现代温暖场景，清晨柔和阳光洒在前景浅米色洞石"
                f"或温润原木桌面上，大光圈 f/1.8 奶油虚化背景，前景桌面中央留出干净空位便于合成「{prod_name}」官方盒瓶原图。"
                f"纯摄影背景，无人物、无产品包装、无文字、无水印。"
            )
            p_vid = ""
        else:
            p_img = (
                f"高端商业电商主图摄影，16:9 宽银幕。围绕「{title}」（{sub or vo}），展现「{prod_name}」的真实使用氛围与质感，"
                f"光线高级通透，画面留出标题安全区，无文字、无水印。"
            )
            p_vid = ""

        packs.append({
            "id": sc.get("id", f"s{idx + 1:02d}"),
            "group": f"{group}（{badge or sc.get('id', '')}）",
            "title": f"第 {idx + 1} 幕 · {title}",
            "ratio": ratio,
            "recommended_model": model,
            "prompt_image": p_img,
            "prompt_video": p_vid,
        })

    return packs


def build_prompt_pack(cfg: dict) -> list[dict]:
    if cfg.get("template_mode") == "dynamic" or cfg.get("scenes"):
        return _build_dynamic_prompts(cfg)

    brand = cfg.get("brand", {})
    pains = cfg.get("pain_points", {})
    nutr = cfg.get("nutrients", {})

    cat = brand.get("category_tag", "中老年健康养护")
    p1 = pains.get("pain1_tag", "上下楼梯关节疼、腿疼")
    p2 = pains.get("pain2_tag", "腰疼直不起来")
    p3 = pains.get("pain3_title", "夜间腿脚经常抽筋")

    c1 = nutr.get("card1_analogy", "深海鲨鱼软骨")
    c2 = nutr.get("card2_analogy", "鲜牛奶")
    c3 = nutr.get("card3_analogy", "新鲜鸡蛋黄")
    c4 = nutr.get("card4_analogy", "鲜炖葛根")

    return [
        {
            "id": "01_pain1_frame",
            "group": "痛点实拍首帧 + 图生视频（16:9）",
            "title": f"痛点 1：{p1}",
            "ratio": "16:9",
            "recommended_model": "gemini-3.1-flash-image / 即梦 / 可灵",
            "prompt_image": (
                f"16:9 宽银幕 35mm 电影商业摄影质感，主题：{cat}。"
                f"一位 60 岁左右的真实中国中老年男性，身穿柔和米色针织开衫，在温暖晨光洒入的居家木质楼梯上缓慢上楼，"
                f"一手紧握扶手，另一手轻按膝盖，神情真实克制、体现「{p1}」的不适感。"
                f"现代温馨中式室内背景柔和虚化，浅景深，自然皮肤质感，无文字，无 Logo，无水印。"
            ),
            "prompt_video": (
                f"真实 35mm 电影商拍质感，5 秒 16:9。老人紧握楼梯扶手上楼时微微停顿，皱眉低头轻按揉膝盖，体现「{p1}」。"
                f"镜头极缓慢平稳微推，窗外晨光自然柔和，动作克制自然不夸张，无字幕无水印。"
            ),
        },
        {
            "id": "02_pain2_frame",
            "group": "痛点实拍首帧 + 图生视频（16:9）",
            "title": f"痛点 2：{p2}",
            "ratio": "16:9",
            "recommended_model": "gemini-3.1-flash-image / 即梦 / 可灵",
            "prompt_image": (
                f"16:9 宽银幕 35mm 电影商业摄影质感。一位 58 岁左右的真实中国女性，身穿柔和鼠尾草绿针织毛衣，"
                f"站在阳光洒满的中国家庭客厅木桌旁，一手扶桌沿，另一手轻扶后腰，面露克制真实的「{p2}」僵硬神情。"
                f"清晨柔和窗光透过白纱窗帘，浅景深虚化，无文字，无 Logo，无水印。"
            ),
            "prompt_video": (
                f"真实 35mm 电影商拍质感，5 秒 16:9。阿姨扶着木桌边缘缓缓起身，另一只手扶住后腰轻轻按压揉动，微微皱眉轻叹，"
                f"镜头极缓慢平稳微推，晨光柔和自然，无字幕无水印。"
            ),
        },
        {
            "id": "03_pain3_video",
            "group": "痛点实拍首帧 + 图生视频（16:9）",
            "title": f"痛点 3：{p3}",
            "ratio": "16:9",
            "recommended_model": "可灵 / 即梦 / Seedance / Google Flow",
            "prompt_image": (
                f"16:9 宽银幕 35mm 电影商业摄影质感。深夜温馨的中国家庭卧室，床头一盏暖黄色台灯柔和亮着。"
                f"一位 60 岁左右穿着素雅浅灰棉质睡衣的中国老人坐在床沿，微皱眉头俯身轻握揉按小腿与脚踝，体现「{p3}」。"
                f"浅景深虚化，光线温暖克制不昏暗，无文字，无水印。"
            ),
            "prompt_video": (
                f"真实 35mm 电影商拍质感，5 秒 16:9。深夜暖黄台灯卧室，穿浅灰睡衣的老人坐在床沿微皱眉头，"
                f"双手紧握并轻轻揉按抽筋的小腿肚和脚踝，镜头极缓慢平稳微推，光线温暖写实，无字幕无水印。"
            ),
        },
        {
            "id": "04_tabletop_bg",
            "group": "大牌产品实景背景（16:9）",
            "title": "暖阳洞石/原木客厅桌面背景",
            "ratio": "16:9",
            "recommended_model": "GPT Image (gpt-image-1) / Midjourney / 即梦",
            "prompt_image": (
                "真实高端商业广告实景背景摄影，16:9 横屏。明亮通透的现代温暖客厅，清晨柔和阳光透过亚麻白纱窗帘洒在前景浅米色洞石"
                "与温润橡木桌面上，大光圈 f/1.8 奶油虚化背景，前景桌面中央与中下部留出大面积干净空位便于摆放产品盒瓶。"
                "纯摄影画面，无人物、无产品包装、无文字、无水印。"
            ),
            "prompt_video": "",
        },
        {
            "id": "05_ingredient_macros",
            "group": "营养类比与核心成分静物（1:1 纯白底）",
            "title": f"四组核心营养静物（{c1} / {c2} / {c3} / {c4}）",
            "ratio": "1:1",
            "recommended_model": "GPT Image (gpt-image-1) / 即梦",
            "prompt_image": (
                f"高端营养杂志商业微距棚拍摄影，1:1 方图，风格统一。主体分别拍摄：\n"
                f"1) {c1}：盛放在极简哑光白瓷浅碟中，洁净通透带自然光泽；\n"
                f"2) {c2}：极简透明玻璃杯盛装，质感温润洁净；\n"
                f"3) {c3}：盛放在极简浅口白瓷碟中，光泽饱满温润；\n"
                f"4) {c4}：新鲜切片搭配两片嫩绿草本叶，呈现温和东方草本科研质感。\n"
                f"通用约束：柔和暖白漫反射棚拍光，完全隔离在纯平坦纯白背景（#FFFFFF）上，无地面阴影、无餐具、无文字、无水印，主体居中占画幅 65%–70%。"
            ),
            "prompt_video": "",
        },
    ]
