# lootlabs_bypass.py
import re, json, time, base64, hashlib, random, string
import requests
import websocket
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def _rand_id(n=16):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))

def _botd_payload(site_key: str) -> str:
    key = hashlib.sha256(site_key.encode()).digest()
    aes = AESGCM(key)
    nonce = bytes(random.getrandbits(8) for _ in range(12))
    body = json.dumps({"ua": UA, "platform": "Win32", "ts": int(time.time()*1000), "r": _rand_id(32)}).encode()
    ct = aes.encrypt(nonce, body, None)
    return base64.b64encode(nonce + ct).decode()

def _extract_task_id(url: str) -> str:
    m = re.search(r"[?&](?:data|id|task|t)=([^&#]+)", url)
    if m: return m.group(1)
    return url.rstrip("/").split("/")[-1].split("?")[0]

def getDest(url: str, timeout: int = 20) -> str:
    # 1. 获取页面与 sitekey
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    r = s.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    m = re.search(r'data-sitekey="([^"]+)"', r.text)
    site_key = m.group(1) if m else ""

    # 2. 提取 WebSocket 地址（LootLabs 内部任务通道）
    ws_match = re.search(r'(wss?://[^\s"\']+)', r.text)
    if not ws_match:
        raise ValueError("未找到 WebSocket 端点")
    ws_url = ws_match.group(1)

    task_id = _extract_task_id(url)
    token = _botd_payload(site_key)

    # 3. 通过 WebSocket 发送任务完成消息
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout)
        ws.send(json.dumps({"task": task_id, "token": token, "ua": UA, "ts": int(time.time()*1000)}))
        resp = ws.recv()
        ws.close()
    except Exception as e:
        raise ValueError(f"WebSocket 通信失败: {e}")

    try:
        data = json.loads(resp)
    except json.JSONDecodeError:
        raise ValueError(f"WebSocket 返回非 JSON: {resp}")

    dest = data.get("destination") or data.get("dest") or data.get("url")
    if not isinstance(dest, str) or not dest.startswith("http"):
        raise ValueError(f"未解析出目标链接: {data}")
    return dest
