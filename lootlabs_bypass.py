# lootlabs_bypass.py
# LootLabs bypass —— 直接对接 LootLabs 内部流程，不经过任何第三方 bypass API
# 逻辑参考公开逆向成果（AJYates/LootLabs_Bypass 等）
import re
import json
import time
import base64
import hashlib
import random
import string

import requests
from bs4 import BeautifulSoup

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    AESGCM = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

BASE_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _session():
    s = requests.Session()
    s.headers.update(BASE_HEADERS)
    return s


def _rand_id(n=16):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _botd_payload(site_key: str) -> str:
    """
    构造一个最小的 BotD 载荷。LootLabs 会用 AES-GCM 解这个串。
    这里的实现不保证 100% 与最新版本对齐，但结构正确。
    """
    if AESGCM is None:
        return base64.b64encode(b"{}").decode()

    key = hashlib.sha256(site_key.encode()).digest()
    aes = AESGCM(key)
    nonce = bytes(random.getrandbits(8) for _ in range(12))
    body = json.dumps({
        "ua": UA,
        "platform": "Win32",
        "vendor": "Google Inc.",
        "ts": int(time.time() * 1000),
        "r": _rand_id(32),
    }).encode()
    ct = aes.encrypt(nonce, body, None)
    return base64.b64encode(nonce + ct).decode()


def _extract_task_id(url: str) -> str:
    # loot-link.com/s?xxxx 或 lootlabs.gg/xxxx
    m = re.search(r"[?&](?:data|id|task|t)=([^&#]+)", url)
    if m:
        return m.group(1)
    tail = url.rstrip("/").split("/")[-1].split("?")[0]
    return tail


def getDest(url: str, timeout: int = 20) -> str:
    """
    传入 LootLabs 链接，返回最终目标 URL。
    失败时抛异常，由 bypass_service 统一捕获。
    """
    s = _session()

    # 1) 打开页面，拿 sitekey 和内部配置
    r = s.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    html = r.text

    m = re.search(r'data-sitekey="([^"]+)"', html)
    site_key = m.group(1) if m else ""

    # 2) 提取可能的内部接口地址（不同版本字段名会变）
    m2 = re.search(r'"api"\s*:\s*"([^"]+)"', html)
    api_base = m2.group(1) if m2 else "https://lootlabs.gg/api"

    task_id = _extract_task_id(url)
    payload = {
        "task": task_id,
        "token": _botd_payload(site_key),
        "ua": UA,
        "ts": int(time.time() * 1000),
    }

    # 3) 向内部接口请求 dest
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://lootlabs.gg",
        "Referer": url,
    }

    endpoints = [
        f"{api_base}/task/complete",
        f"{api_base}/task/verify",
        f"{api_base}/v1/task",
    ]

    last_err = None
    for ep in endpoints:
        try:
            resp = s.post(ep, json=payload, headers=headers, timeout=timeout)
            if resp.status_code >= 400:
                last_err = f"{ep} -> HTTP {resp.status_code}"
                continue
            data = resp.json()
            dest = data.get("destination") or data.get("dest") or data.get("url")
            if isinstance(dest, str) and dest.startswith("http"):
                return dest
        except Exception as e:
            last_err = f"{ep} -> {type(e).__name__}: {e}"

    raise ValueError(f"LootLabs 未解析出目标链接（{last_err or 'no endpoint matched'}）")
