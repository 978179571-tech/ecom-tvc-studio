"""Multi-category e-commerce advertising compliance linter (2.0).

Supports category modes via cfg["category"]:
  - "medical_device": Class I/II external medical devices & patches (registration no + mandatory medical advisory + anti-cure/comparative superlatives)
  - "blue_hat": Chinese blue-hat health supplements (strictest: medical bans + approval_no + mandatory disclaimer)
  - "food" / "functional_food": Functional / general food (medical bans + absolute superlatives)
  - "skincare": Skincare & personal care (medical/cure bans + absolute superlatives)
  - "general": General e-commerce (China Ad Law absolute superlatives & comparative disparagement bans)
"""

from __future__ import annotations
import re

ABSOLUTE_BANNED_WORDS = [
    "最有效", "第一品牌", "全网第一", "销量第一", "国家级唯一",
    "绝对安全", "100%有效", "100%治愈", "顶级", "极致唯一", "永久有效",
]

COMPARATIVE_BANNED_WORDS = [
    "高于普通", "普通膏贴两倍", "两倍以上", "优于同行", "秒杀同类", "吊打", "完胜普通",
]

MEDICAL_BANNED_WORDS = [
    "根治", "治愈", "包治", "特效", "神效", "药效", "消炎", "镇痛",
    "替代药物", "代替药物", "临床治愈", "彻底解决", "一吃就好", "立竿见影",
    "治好", "疗程", "抗癌", "防癌", "降血压", "降血糖",
]

DEVICE_BANNED_CURE_WORDS = [
    "根治", "包治", "治愈率", "100%好转", "彻底治愈", "永不复发",
    "神效", "特效药", "一贴断根", "立竿见影", "药到病除",
]

REQUIRED_BLUE_HAT_DISCLAIMER = "保健食品不是药物，不能代替药物治疗疾病"
REQUIRED_DEVICE_ADVISORY = "请仔细阅读产品说明书或者在医务人员的指导下购买和使用"

CATEGORY_LABELS = {
    "medical_device": "二类/外用医疗器械",
    "blue_hat": "蓝帽保健食品",
    "food": "功能/普通食品",
    "functional_food": "功能性食品/膳食营养",
    "skincare": "功效护肤/个护",
    "general": "通用电商",
}

SKIP_KEYS = {
    "media", "media_alt", "media_slot", "frame_slot", "id", "type", "voice",
    "vp_mode", "sub_style", "trans_in", "layout_mode", "viewport_ratio",
    "custom_prompt_image", "custom_prompt_video", "prompt_ratio", "prompt_model", "prompt_group",
}

SKIP_PATHS = {
    "brand.compliance_footer", "category", "template_mode", "project_id",
}


def check_compliance(cfg: dict) -> dict:
    """Validate project config text against category-appropriate ad compliance rules."""
    category = str(cfg.get("category") or "general").strip().lower()
    if category not in CATEGORY_LABELS:
        category = "general"

    issues: list[dict] = []
    warnings: list[dict] = []

    brand = cfg.get("brand") or {}
    footer = str(brand.get("compliance_footer", "")).strip()
    approval_no = str(brand.get("approval_no", "")).strip()

    if category == "blue_hat":
        if REQUIRED_BLUE_HAT_DISCLAIMER not in footer:
            issues.append({
                "field": "brand.compliance_footer",
                "level": "error",
                "message": f"蓝帽保健食品缺少法规必填声明：「{REQUIRED_BLUE_HAT_DISCLAIMER}」",
            })
        if not approval_no:
            warnings.append({
                "field": "brand.approval_no",
                "level": "warning",
                "message": "未填写蓝帽批准文号（如 国食健注GXXXXXXXX），建议补充。",
            })

    elif category == "medical_device":
        if REQUIRED_DEVICE_ADVISORY not in footer:
            issues.append({
                "field": "brand.compliance_footer",
                "level": "error",
                "message": f"医疗器械缺少法定忠告语：「{REQUIRED_DEVICE_ADVISORY}」",
            })
        combined_reg = f"{approval_no} {footer}"
        if not re.search(r"(械注准|械备)\d{6,}", combined_reg):
            issues.append({
                "field": "brand.approval_no",
                "level": "error",
                "message": "医疗器械未标注注册证编号或备案号（如 X械注准XXXXXXXXXXX）。",
            })

    banned = list(ABSOLUTE_BANNED_WORDS) + list(COMPARATIVE_BANNED_WORDS)
    check_treatment = False
    if category in ("blue_hat", "food", "functional_food", "skincare"):
        banned.extend(MEDICAL_BANNED_WORDS)
        check_treatment = True
    elif category == "medical_device":
        banned.extend(DEVICE_BANNED_CURE_WORDS)

    def scan_obj(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                if path in SKIP_PATHS or k in SKIP_KEYS:
                    continue
                if isinstance(v, (int, float, bool)) or v is None:
                    continue
                scan_obj(v, path)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                scan_obj(item, f"{prefix}[{idx}]")
        elif isinstance(obj, str):
            for word in banned:
                if word in obj:
                    issues.append({
                        "field": prefix,
                        "level": "error",
                        "message": f"包含违规绝对化/拉踩/夸大词「{word}」：{obj}",
                    })
            if check_treatment and "治疗" in obj:
                issues.append({
                    "field": prefix,
                    "level": "error",
                    "message": f"非器械品类严禁出现「治疗」用语：{obj}",
                })

    scan_obj(cfg)

    return {
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "passed": len(issues) == 0,
        "error_count": len(issues),
        "warning_count": len(warnings),
        "issues": issues,
        "warnings": warnings,
    }
