"""Generate ready-to-copy Chinese image & image-to-video prompts from project.json."""


def build_prompt_pack(cfg: dict) -> list[dict]:
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
