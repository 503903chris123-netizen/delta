
import re
import requests
from urllib.parse import urlparse

LINKVERTISE_PATTERNS = [
    r"(^|\.)linkvertise\.com$", r"(^|\.)linkvertise\.net$",
    r"(^|\.)link-to\.net$", r"(^|\.)link-hub\.net$",
    r"(^|\.)link-center\.net$", r"(^|\.)link-target\.net$",
    r"(^|\.)linkunlock\.com$", r"(^|\.)direct-link\.net$",
]

LOOTLABS_PATTERNS = [
    r"(^|\.)lootlabs\.gg$", r"(^|\.)loot-link\.com$",
    r"(^|\.)loot-links\.com$", r"(^|\.)lootlink\.org$",
    r"(^|\.)lootdest\.org$", r"(^|\.)lootdest\.com$",
    r"(^|\.)lootdest\.info$", r"(^|\.)lootlinks\.co$",
]


def detect_service(url: str):
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
    service = detect_service(url)
    if service is None:
        return {
            "success": False,
            "destination": None,
            "service": None,
            "message": "不支持该类型：仅支持 Linkvertise 和 Lootlabs 的链接。",
        }

    try:
        resp = requests.post(
            "https://api.bypass.vip/",
            data={"url": url},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return {"success": False, "destination": None, "service": service, "message": "请求超时，请稍后重试。"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "destination": None, "service": service, "message": f"网络请求失败：{str(e)}"}
    except ValueError:
        return {"success": False, "destination": None, "service": service, "message": "API 返回了无效的数据格式。"}

    destination = data.get("result") or data.get("destination")
    if not destination or not isinstance(destination, str) or not destination.startswith("http"):
        api_msg = data.get("message") or data.get("msg") or "API 未返回有效的目标链接。"
        return {"success": False, "destination": None, "service": service, "message": f"解析失败（{service}）：{api_msg}"}

    return {"success": True, "destination": destination, "service": service, "message": "ok"}
