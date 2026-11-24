
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Delta Cardkey HTTP API
# 启动: python server.py --port 2233

import sys, os, time, asyncio, argparse, hashlib, threading, json
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

try:
    from fastapi.responses import ORJSONResponse as JSONResponse
except Exception:
    from fastapi.responses import JSONResponse

from main import solve_chain
from auth_client import extract_ticket, MIN_TICKET_LEN
from link_generator import batch_links
import auth_client as AUTH
from bypass_service import bypass_url

app = FastAPI(title="Delta Cardkey", default_response_class=JSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=10)
lock = threading.Lock()

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".key_cache.json")
key_cache = {}
CACHE_TTL = 24 * 3600
cache_dirty = threading.Event()
SAVE_DEBOUNCE = 2.0


def load_cache():
    global key_cache
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                data = json.load(f)
            now = time.time()
            key_cache = {h: v for h, v in data.items() if isinstance(v, dict) and now - v.get("ts", 0) < CACHE_TTL}
    except Exception:
        key_cache = {}


def save_cache_now():
    try:
        with lock:
            now = time.time()
            for h in [h for h, v in key_cache.items() if now - v.get("ts", 0) >= CACHE_TTL]:
                key_cache.pop(h, None)
            snapshot = dict(key_cache)
            tmp = CACHE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(snapshot, f)
            os.replace(tmp, CACHE_FILE)
    except Exception:
        pass


def cache_writer_loop():
    while True:
        cache_dirty.wait()
        time.sleep(SAVE_DEBOUNCE)
        cache_dirty.clear()
        save_cache_now()


def cache_get(ticket, h=None):
    h = h or hashlib.md5(ticket.encode()).hexdigest()
    with lock:
        rec = key_cache.get(h)
        if rec:
            if time.time() - rec.get("ts", 0) < CACHE_TTL:
                return rec.get("key"), True, rec.get("solve_time", 0.0)
            key_cache.pop(h, None)
    return None, False, 0.0


def cache_put(ticket, key, solve_time, h=None):
    if not key:
        return
    h = h or hashlib.md5(ticket.encode()).hexdigest()
    with lock:
        key_cache[h] = {"key": key, "ts": time.time(), "solve_time": solve_time}
    cache_dirty.set()


load_cache()
threading.Thread(target=cache_writer_loop, daemon=True).start()

MADE_BY = "Hasl_Team"
QQ_GROUP = "277707901"
inflight = {}


def fmt_t(secs):
    return f"{round(float(secs or 0.0), 12)}s"


# ===== 原有解 Key 逻辑保持不变，只展示关键路由骨架 =====
# 你的 solo_pass / 缓存 / 批量解等函数原样保留即可，这里不重复粘贴。
# 下面的 /api/bypass 是新增的。


@app.post("/api/bypass")
async def api_bypass(payload: dict):
    url = (payload or {}).get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="请求体必须包含 url 字段。")

    result = bypass_url(url)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


# ===== 你原有的 /api/solve /api/batch 等路由全部保留在此下方 =====
# 只需把上面这个 /api/bypass 插入到任意合适位置即可，不要删除原有代码。
