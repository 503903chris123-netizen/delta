import re
import requests
from urllib.parse import urlparse

from lootlabs_bypass import getDest as lootlabs_getDest

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


# ---------------- Linkvertise 纯 requests 实现 ----------------
LV_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Content-Type": "application/json",
}


def bypass_linkvertise(url: str) -> str:
    m = re.search(r"linkvertise\.com/(\d+/.+?)(?:\?|$)", url)
    if not m:
        raise ValueError("不是 linkvertise.download 风格的链接")
    link_stuff = m.group(1)
    key = url.rstrip("/").split("/")[-1].split("?")[0]

    r = requests.post(
        f"https://publisher.linkvertise.com/api/v1/redirect/link/{link_stuff}/download-info",
        json={"key": key},
        headers=LV_HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    download_url = r.json()["data"]["downloadUrl"]

    head = requests.head(download_url, headers=LV_HEADERS,
                         timeout=10, allow_redirects=True)
    cd = head.headers.get("content-disposition", "")
    name_match = re.search(r"Downloader_([^ .]+)", cd)
    if not name_match:
        raise ValueError("无法从下载器响应中提取文件名")
    name = name_match.group(1)

    r2 = requests.post(
        "https://d17kz3i6hbr7d3.cloudfront.net/o",
        json={
            "prv": "0.1",
            "plv": "1.34.2.8157",
            "l": "en", "a": "Linkvertise",
            "i": "Linkvertise_DLM", "s": "Linkvertise",
            "u": name, "o": "10",
        },
        headers=LV_HEADERS,
        timeout=15,
    )
    r2.raise_for_status()
    return r2.json()["i"]["cu"]


# ---------------- LootLabs 通过内联模块 ----------------
def bypass_lootlabs(url: str) -> str:
    return lootlabs_getDest(url)


# ---------------- 统一入口 ----------------
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
        if service == "linkvertise":
            destination = bypass_linkvertise(url)
        elif service == "lootlabs":
            destination = bypass_lootlabs(url)
        else:
            return {"success": False, "destination": None,
                    "service": service, "message": "不支持该类型。"}
    except Exception as e:
        return {
            "success": False,
            "destination": None,
            "service": service,
            "message": f"自行解析失败（{service}）：{type(e).__name__}: {e}",
        }

    if not destination or not isinstance(destination, str) or not destination.startswith("http"):
        return {"success": False, "destination": None,
                "service": service, "message": "未解析出有效目标链接。"}

    return {"success": True, "destination": destination,
            "service": service, "message": "ok"}
