"""Multi-category e-commerce advertising compliance linter.

Supports category modes via cfg["category"]:
  - "blue_hat": Chinese blue-hat health supplements (strictest: medical bans + approval_no + mandatory disclaimer)
  - "food": Functional / general food (medical bans + absolute superlatives)
  - "skincare": Skincare & beauty (medical/cure bans + absolute superlatives)
  - "general": General e-commerce (China Ad Law absolute superlatives only)
"""

from __future__ import annotations

ABSOLUTE_BANNED_WORDS = [
    "最有效", "第一品牌", "全网第一", "销量第一", "国家级唯一",
    "绝对安全", "100%有效", "顶级", "极致唯一", "永久有效",
]

MEDICAL_BANNED_WORDS = [
    "根治", "治愈", "包治", "特效", "神效", "药效", "消炎", "镇痛",
    "替代药物", "代替药物", "临床治愈", "彻底解决", "一吃就好", "立竿见影",
    "治好", "疗程", "抗癌", "防癌", "降血压", "降血糖",
]

REQUIRED_BLUE_HAT_DISCLAIMER = "保健食品不是药物，不能代替药物治疗疾病。"

CATEGORY_LABELS = {
    "blue_hat": "蓝帽保健食品",
    "food": "普通/功能食品",
    "skincare": "护肤美妆",
    "general": "通用电商",
}


def check_compliance(cfg: dict) -> dict:
    """Validate project config text against category-appropriate ad compliance rules."""
    category = str(cfg.get("category") or "blue_hat").strip().lower()
    if category not in CATEGORY_LABELS:
        category = "general"

    issues: list[dict] = []
    warnings: list[dict] = []

    brand = cfg.get("brand") or {}
    footer = str(brand.get("compliance_footer", "")).strip()

    if category == "blue_hat":
        if REQUIRED_BLUE_HAT_DISCLAIMER not in footer:
            issues.append({
                "field": "brand.compliance_footer",
                "level": "error",
                "message": f"蓝帽保健食品缺少法规必填声明：「{REQUIRED_BLUE_HAT_DISCLAIMER}」",
            })
        approval_no = str(brand.get("approval_no", "")).strip()
        if not approval_no:
            warnings.append({
                "field": "brand.approval_no",
                "level": "warning",
                "message": "未填写蓝帽批准文号（如 国食健注 G20090546），建议补充以提升信任度。",
            })

    banned = list(ABSOLUTE_BANNED_WORDS)
    check_treatment = False
    if category in ("blue_hat", "food", "skincare"):
        banned.extend(MEDICAL_BANNED_WORDS)
        check_treatment = True

    def scan_obj(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                if path in ("brand.compliance_footer", "category", "template_mode", "project_id"):
                    continue
                if k in ("media", "media_slot", "id", "type", "voice"):
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
                        "message": f"包含高风险违规/绝对化词「{word}」：{obj}",
                    })
            if check_treatment and "治疗" in obj:
                issues.append({
                    "field": prefix,
                    "level": "error",
                    "message": f"非声明字段包含医疗词「治疗」：{obj}",
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
