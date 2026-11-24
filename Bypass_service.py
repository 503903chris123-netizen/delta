import re
from urllib.parse import urlparse
from PyBypass import bypasser

# 支持自动识别的域名列表
LINKVERTISE_PATTERNS = [
    r"(^|\.)linkvertise\.com$",
    r"(^|\.)linkvertise\.net$",
    r"(^|\.)link-to\.net$",
    r"(^|\.)link-hub\.net$",
    r"(^|\.)link-center\.net$",
    r"(^|\.)link-target\.net$",
    r"(^|\.)linkunlock\.com$",
    r"(^|\.)direct-link\.net$",
]

LOOTLABS_PATTERNS = [
    r"(^|\.)lootlabs\.gg$",
    r"(^|\.)loot-link\.com$",
    r"(^|\.)loot-links\.com$",
    r"(^|\.)lootlink\.org$",
    r"(^|\.)lootdest\.org$",
    r"(^|\.)lootdest\.com$",
    r"(^|\.)lootdest\.info$",
    r"(^|\.)lootlinks\.co$",
]


def detect_service(url: str) -> str | None:
    """
    自动识别链接所属的服务。
    返回 'linkvertise' / 'lootlabs'，不支持则返回 None。
    """
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return None

    for pattern in LINKVERTISE_PATTERNS:
        if re.search(pattern, hostname, re.IGNORECASE):
            return "linkvertise"

    for pattern in LOOTLABS_PATTERNS:
        if re.search(pattern, hostname, re.IGNORECASE):
            return "lootlabs"

    return None


def bypass_url(url: str) -> dict:
    """
    核心 bypass 函数。
    返回格式：
    { "success": bool, "destination": str|None, "service": str|None, "message": str }
    """
    service = detect_service(url)

    if service is None:
        return {
            "success": False,
            "destination": None,
            "service": None,
            "message": "不支持该类型：仅支持 Linkvertise 和 Lootlabs 的链接。",
        }

    try:
        destination = bypasser.bypass(url, name=service)
    except Exception as e:
        return {
            "success": False,
            "destination": None,
            "service": service,
            "message": f"bypass 失败（{service}）：{str(e)}",
        }

    if not destination or not isinstance(destination, str) or not destination.startswith("http"):
        return {
            "success": False,
            "destination": None,
            "service": service,
            "message": f"bypass 未返回有效的目标链接（{service}）。",
        }

    return {
        "success": True,
        "destination": destination,
        "service": service,
        "message": "ok",
    }
