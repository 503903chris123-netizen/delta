# lootlabs_bypass.py
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
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def _rand_id(n=16):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))

def _botd_payload(site_key: str) -> str:
    if AESGCM is None:
        return ""
    key = hashlib.sha256(site_key.encode()).digest()
    aes = AESGCM(key)
    nonce = bytes(random.getrandbits(8) for _ in range(12))
    body = json.dumps({
        "ua": UA, "platform": "Win32", "ts": int(time.time()*1000), "r": _rand_id(32)
    }).encode()
    ct = aes.encrypt(nonce, body, None)
    return base64.b64encode(nonce + ct).decode()

def getDest(url: str, timeout: int = 25) -> str:
    """
    多策略尝试解析 LootLabs 链接，按顺序执行直到成功。
    策略1：直接跟随重定向（部分短链有效）
    策略2：curl_cffi 模拟浏览器（绕过部分 TLS 指纹检测）
    策略3：解析页面，寻找 WebSocket 端点并尝试连接
    策略4：在页面 HTML / 内联 JSON 中搜索目的地 URL
    """
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

    # ---------- 策略1：直接跟随重定向 ----------
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        if resp.url != url and "lootlabs" not in resp.url and "loot-link" not in resp.url:
            if resp.url.startswith("http"):
                return resp.url
    except Exception:
        pass

    # ---------- 策略2：curl_cffi 模拟浏览器 ----------
    if HAS_CURL_CFFI:
        try:
            cffi_resp = curl_requests.get(url, impersonate="chrome124", timeout=timeout, allow_redirects=True)
            if cffi_resp.url != url and "lootlabs" not in cffi_resp.url and "loot-link" not in cffi_resp.url:
                if cffi_resp.url.startswith("http"):
                    return cffi_resp.url
            html = cffi_resp.text
        except Exception:
            html = None
    else:
        html = None

    if html is None:
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            html = resp.text
        except Exception as e:
            raise ValueError(f"无法获取页面内容: {e}")

    # ---------- 策略3：寻找 WebSocket 端点并尝试连接 ----------
    ws_match = re.search(r'(wss?://[^\s"\']+)', html)
    if ws_match:
        ws_url = ws_match.group(1)
        task_id = _extract_task_id(url)
        site_key_match = re.search(r'data-sitekey="([^"]+)"', html)
        site_key = site_key_match.group(1) if site_key_match else ""
        token = _botd_payload(site_key)

        try:
            import websocket
            ws = websocket.create_connection(ws_url, timeout=timeout)
            ws.send(json.dumps({"task": task_id, "token": token, "ua": UA, "ts": int(time.time()*1000)}))
            raw = ws.recv()
            ws.close()
            data = json.loads(raw)
            dest = data.get("destination") or data.get("dest") or data.get("url")
            if isinstance(dest, str) and dest.startswith("http"):
                return dest
        except Exception:
            pass

    # ---------- 策略4：在页面中搜索目的地 URL ----------
    # 4.1 查找内联 JSON 中的 destination / url 字段
    for pattern in [
        r'"destination"\s*:\s*"([^"]+)"',
        r'"dest"\s*:\s*"([^"]+)"',
        r'"redirect"\s*:\s*"([^"]+)"',
        r'"url"\s*:\s*"([^"]+)"',
    ]:
        m = re.search(pattern, html)
        if m:
            candidate = m.group(1).replace("\\/", "/")
            if candidate.startswith("http") and "lootlabs" not in candidate:
                return candidate

    # 4.2 查找 <a> 标签中看起来像目的地的链接
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and "lootlabs" not in href and "loot-link" not in href:
            # 过滤掉常见的资源链接
            if not re.search(r"\.(css|js|png|jpg|svg|woff2?)$", href, re.I):
                return href

    raise ValueError(
        "LootLabs 解析失败：所有策略均未找到目标链接。"
        "这条链接可能启用了强 Cloudflare 保护或新的 BotD 校验，"
        "建议安装 `curl_cffi` 后重试（pip install curl_cffi）。"
    )

def _extract_task_id(url: str) -> str:
    m = re.search(r"[?&](?:data|id|task|t)=([^&#]+)", url)
    if m:
        return m.group(1)
    return url.rstrip("/").split("/")[-1].split("?")[0]
