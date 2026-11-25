"""Blue-Hat health supplement & e-commerce advertising compliance linter."""

BANNED_MEDICAL_WORDS = [
    "根治", "治愈", "包治", "特效", "神效", "药效", "消炎", "镇痛",
    "替代药物", "代替药物", "临床治愈", "彻底解决", "一吃就好", "立竿见影",
    "最有效", "第一品牌", "国家级唯一", "绝对安全", "100%有效", "治好", "疗程",
]

REQUIRED_DISCLAIMER = "保健食品不是药物，不能代替药物治疗疾病。"


def check_compliance(cfg: dict) -> dict:
    """Validate project config text against blue-hat health supplement ad rules."""
    issues = []
    warnings = []

    footer = (cfg.get("brand") or {}).get("compliance_footer", "").strip()
    if REQUIRED_DISCLAIMER not in footer:
        issues.append({
            "field": "brand.compliance_footer",
            "level": "error",
            "message": f"缺少法规必填声明：「{REQUIRED_DISCLAIMER}」",
        })

    def scan_obj(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                if path == "brand.compliance_footer":
                    continue
                scan_obj(v, path)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                scan_obj(item, f"{prefix}[{idx}]")
        elif isinstance(obj, str):
            for word in BANNED_MEDICAL_WORDS:
                if word in obj:
                    issues.append({
                        "field": prefix,
                        "level": "error",
                        "message": f"包含高风险医疗/绝对化禁用词「{word}」：{obj}",
                    })
            if "治疗" in obj:
                issues.append({
                    "field": prefix,
                    "level": "error",
                    "message": f"非声明字段包含医疗词「治疗」：{obj}",
                })

    scan_obj(cfg)

    approval_no = (cfg.get("brand") or {}).get("approval_no", "").strip()
    if not approval_no:
        warnings.append({
            "field": "brand.approval_no",
            "level": "warning",
            "message": "未填写蓝帽批准文号（如 国食健注 G20090546），建议补充以提升信任度。",
        })

    return {
        "passed": len(issues) == 0,
        "error_count": len(issues),
        "warning_count": len(warnings),
        "issues": issues,
        "warnings": warnings,
    }
