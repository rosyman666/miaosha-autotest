# -*- coding: utf-8 -*-
"""请求层：Requests 会话封装。

所有用例不直接 import requests，而是通过 ApiClient 发请求。
好处：换域名、加统一日志、加重试、加限流节奏控制，只改这一个文件。

另外两件事也放在这里，因为它们只跟「发请求」有关：
    1. 记录每次请求/响应（用例失败时由 conftest 挂进报告，不用再去翻日志）
    2. trust_env=False：本机开了代理软件时，localhost 请求会被代理转走返回 502，
       看起来像服务挂了。关掉环境变量代理是最省事的解法。
"""
import time
from typing import Any, Dict, List

import requests

from common.reporting import render_exchange

MAX_BODY_CHARS = 3000


def _shorten(text: str, limit: int = MAX_BODY_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n...(已截断，共 {len(text)} 字符)"


def _mask_cookie(raw: str) -> str:
    """token 只留前 8 位：报告要能看出「有没有下发」，不需要能复用它。"""
    if raw.startswith("token=") and len(raw) > 14:
        return f"token={raw[6:14]}...(已脱敏)"
    return raw


class ApiClient:
    """一个 ApiClient = 一个独立会话（自动管理 Cookie）。"""

    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False  # 绕开系统代理，见模块注释
        self.exchanges: List[Dict[str, Any]] = []
        self._calls: Dict[str, List[float]] = {}

    # ---------- 基础方法 ----------
    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = self.base_url + path
        kwargs.setdefault("timeout", self.timeout)
        started = time.perf_counter()
        resp = self.session.request(method.upper(), url, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._record(method.upper(), url, kwargs, resp, elapsed_ms)
        return resp

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.request("POST", path, **kwargs)

    # ---------- 业务方法 ----------
    def login(self, mobile: str, password_cipher: str) -> requests.Response:
        """登录：密码传前端加密后的密文（双层加盐 MD5），成功后 token 写入 Cookie。"""
        return self.post(
            "/login/do_login",
            data={"mobile": mobile, "password": password_cipher},
        )

    @property
    def token(self) -> str:
        return self.session.cookies.get("token", "")

    # ---------- 限流节奏 ----------
    def wait_rate(self, key: str, seconds: int, max_count: int) -> float:
        """在触发接口 @AccessLimit(seconds, maxCount) 之前主动等一会儿。

        秒杀系统的限流是「seconds 秒内最多 maxCount 次」，计数 key 是
        requestURI + 用户名（不含 query）。用例连着打同一个接口很容易撞上限流，
        失败信息又长得像业务错误，排查成本高。这里按记录的调用时间戳提前让路，
        留一次余量，保证用例只在「确实要测限流」时才打满。
        返回实际等待的秒数。
        """
        now = time.time()
        recent = [t for t in self._calls.get(key, []) if now - t < seconds]
        self._calls[key] = recent
        waited = 0.0
        if len(recent) >= max_count - 1:
            waited = seconds - (now - recent[0]) + 0.05
            if waited > 0:
                time.sleep(waited)
        self._calls.setdefault(key, []).append(time.time())
        return round(waited, 2)

    # ---------- 请求记录 ----------
    def _record(self, method, url, kwargs, resp, elapsed_ms) -> None:
        body = ""
        content_type = resp.headers.get("Content-Type", "")
        if "json" in content_type or "text" in content_type or not content_type:
            try:
                body = resp.text
            except Exception:  # 二进制响应（验证码图片）取不到 text
                body = f"<二进制响应 {len(resp.content)} 字节>"
        else:
            body = f"<{content_type} {len(resp.content)} 字节>"

        self.exchanges.append(
            {
                "ts": time.time(),
                "method": method,
                "url": url,
                "elapsed_ms": round(elapsed_ms, 1),
                "request": {
                    "params": kwargs.get("params"),
                    "form": kwargs.get("data"),
                    "json": kwargs.get("json"),
                    "headers": kwargs.get("headers"),
                    "cookies": [_mask_cookie(f"{c.name}={c.value}") for c in self.session.cookies],
                },
                "response": {
                    "status": resp.status_code,
                    "headers": dict(resp.headers),
                    "body": _shorten(body),
                },
            }
        )

    @property
    def last_exchange(self) -> Dict[str, Any] | None:
        return self.exchanges[-1] if self.exchanges else None

    def render_exchange(self, exchange: Dict[str, Any] | None = None) -> str:
        """把一次请求/响应渲染成可读文本（渲染细节见 common/reporting.py）。"""
        return render_exchange(exchange or self.last_exchange)
