# lootlabs_bypass.py
# LootLabs bypass —— 本地解码 &data= 参数 + WebSocket 任务链回退
# 不经过任何第三方 bypass API

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
except ImportError:
    AESGCM = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _rand_id(n=16):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _botd_payload(site_key: str) -> str:
    """构造 BotD 伪造载荷，用于 WebSocket 回退策略"""
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


def _decode_data_param(url: str):
    """
    尝试本地解码 &data= 参数（XOR 混淆）。
    逻辑来自公开的 LootLabs 绕过脚本，Base64 解码后取前 5 字符作为 XOR 前缀。
    解码成功返回 URL 字符串，失败返回 None。
    """
    data_match = re.search(r'[?&]data=([^&#]+)', url)
    if not data_match:
        return None

    raw = data_match.group(1)
    try:
        # URL 解码后 Base64 解码（补 padding）
        raw = requests.utils.unquote(raw)
        padded = raw + "=" * (-len(raw) % 4)
        decoded_bytes = base64.b64decode(padded)

        if len(decoded_bytes) <= 5:
            return None

        prefix = decoded_bytes[:5]          # 前 5 字节作为 XOR 密钥
        payload = decoded_bytes[5:]         # 剩余部分为密文

        plain = bytes(
            payload[i] ^ prefix[i % len(prefix)]
            for i in range(len(payload))
        )
        candidate = plain.decode("utf-8", errors="ignore")

        if candidate.startswith("http") and "lootlabs" not in candidate:
            return candidate
    except Exception:
        pass
    return None


def getDest(url: str, timeout: int = 25) -> str:
    """
    传入 LootLabs 链接，返回最终目标 URL。
    优先尝试 &data= 本地解码；失败则回退到 WebSocket 任务链解析。
    失败时抛出 ValueError。
    """
    # ---------- 策略 0：直接解码 &data= 参数（最高优先级） ----------
    decoded = _decode_data_param(url)
    if decoded:
        return decoded

    # ---------- 策略 1：获取页面，尝试 WebSocket 任务链 ----------
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        raise ValueError(f"无法获取页面内容: {e}")

    # 尝试寻找 WebSocket 端点并通信
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
            pass  # WebSocket 失败，继续往下

    # ---------- 策略 2：在页面 HTML 中搜索目的地 ----------
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

    raise ValueError(
        "LootLabs 解析失败：&data 本地解码未成功，WebSocket/页面搜索也未找到有效目标。"
        "该链接可能使用了非标准混淆或更强的 BotD 校验。"
    )
