# lootlabs_bypass.py
# LootLabs bypass：
#   策略 A：loot-reward.com/t?cc=  → 双层 Base64 解码直接拿 link（复用你提供的脚本逻辑）
#   策略 B：links.lootlabs.gg/s?...&data=  → 尝试 XOR 混淆解码
#   策略 C：普通任务链 → 页面/WebSocket 回退
# 全程不调用任何第三方 bypass API

import re
import json
import time
import base64
import hashlib
import random
import string
from urllib.parse import urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ============================================================
# 策略 A：loot-reward.com/t?cc= —— 复用你提供的解码逻辑
# ============================================================

def _add_padding(s: str) -> str:
    return s + "=" * (-len(s) % 4)


def _decode_cc(cc: str):
    """双层 Base64 解码 cc 参数，返回 JSON 对象"""
    cc = unquote(cc)
    decoded1 = base64.urlsafe_b64decode(_add_padding(cc)).decode("utf-8", errors="strict")
    if decoded1.startswith("{") or decoded1.startswith("["):
        return json.loads(decoded1)
    decoded2 = base64.b64decode(_add_padding(decoded1)).decode("utf-8")
    return json.loads(decoded2)


def _bypass_loot_reward(url: str):
    """针对 loot-reward.com/t?cc= 链接：直接解码出 link 字段"""
    parsed = urlparse(url)
    if "loot-reward.com" not in (parsed.netloc or ""):
        return None
    params = parse_qs(parsed.query)
    cc_values = params.get("cc")
    if not cc_values:
        return None

    data = _decode_cc(cc_values[0])
    link = data.get("link") if isinstance(data, dict) else None
    if isinstance(link, str) and link.startswith("http"):
        return link
    return None


# ============================================================
# 策略 B：links.lootlabs.gg/s?...&data= —— XOR 混淆尝试
# ============================================================

def _decode_data_param(url: str):
    data_match = re.search(r'[?&]data=([^&#]+)', url)
    if not data_match:
        return None
    raw = data_match.group(1)
    try:
        raw_fixed = raw.replace('+', '%2B')
        raw_decoded = requests.utils.unquote(raw_fixed)
        padded = raw_decoded + "=" * (-len(raw_decoded) % 4)
        decoded_bytes = base64.b64decode(padded)
        if len(decoded_bytes) <= 5:
            return None
        prefix = decoded_bytes[:5]
        payload = decoded_bytes[5:]
        plain = bytes(payload[i] ^ prefix[i % len(prefix)] for i in range(len(payload)))
        candidate = plain.decode("utf-8", errors="ignore")
        if candidate.startswith("http") and "lootlabs" not in candidate:
            return candidate
    except Exception:
        pass
    return None


# ============================================================
# 策略 C：普通任务链 —— BotD + WebSocket / 页面搜索
# ============================================================

def _rand_id(n=16):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _botd_payload(site_key: str) -> str:
    if AESGCM is None:
        return ""
    key = hashlib.sha256(site_key.encode()).digest()
    aes = AESGCM(key)
    nonce = bytes(random.getrandbits(8) for _ in range(12))
    body = json.dumps({
        "ua": UA, "platform": "Win32", "ts": int(time.time() * 1000), "r": _rand_id(32)
    }).encode()
    ct = aes.encrypt(nonce, body, None)
    return base64.b64encode(nonce + ct).decode()


def _extract_task_id(url: str) -> str:
    m = re.search(r"[?&](?:data|id|task|t)=([^&#]+)", url)
    if m:
        return m.group(1)
    return url.rstrip("/").split("/")[-1].split("?")[0]


def _bypass_task_chain(url: str, timeout: int = 25):
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return None

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
            ws.send(json.dumps({
                "task": task_id, "token": token, "ua": UA,
                "ts": int(time.time() * 1000)
            }))
            raw_resp = ws.recv()
            ws.close()
            data = json.loads(raw_resp)
            dest = data.get("destination") or data.get("dest") or data.get("url")
            if isinstance(dest, str) and dest.startswith("http"):
                return dest
        except Exception:
            pass

    for pattern in [
        r'"destination"\s*:\s*"([^"]+)"',
        r'"dest"\s*:\s*"([^"]+)"',
        r'"redirect"\s*:\s*"([^"]+)"',
    ]:
        m = re.search(pattern, html)
        if m:
            cand = m.group(1).replace("\\/", "/")
            if cand.startswith("http") and "lootlabs" not in cand:
                return cand
    return None


# ============================================================
# 统一入口（bypass_service.py 只依赖这个函数）
# ============================================================

def getDest(url: str, timeout: int = 25) -> str:
    """
    依次尝试：
      A. loot-reward.com/t?cc=     → 双层 Base64 解码
      B. ...&data=                 → XOR 混淆解码
      C. 其他                       → WebSocket / 页面搜索
    失败时抛 ValueError。
    """
    # A
    if "loot-reward.com" in url:
        try:
            dest = _bypass_loot_reward(url)
            if dest:
                return dest
        except Exception:
            pass

    # B
    if "&data=" in url or "?data=" in url:
        try:
            dest = _decode_data_param(url)
            if dest:
                return dest
        except Exception:
            pass

    # C
    try:
        dest = _bypass_task_chain(url, timeout=timeout)
        if dest:
            return dest
    except Exception:
        pass

    raise ValueError(
        "LootLabs 解析失败："
        "A) cc 参数解码失败；B) data 参数无法解码；C) 页面未暴露目标链接。"
    )
