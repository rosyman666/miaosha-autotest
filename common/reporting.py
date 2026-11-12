# -*- coding: utf-8 -*-
"""报告展示层：把一次请求/响应渲染成给人看的文本。

单独放一个文件是因为它被两处用：ApiClient（人工调试时打印）和
conftest 的失败钩子（挂进 Allure / pytest-html 附件）。渲染逻辑只写一遍。
"""
import json
from typing import Any, Dict, Optional

INTERESTING_HEADERS = ("content-type", "set-cookie", "location", "content-length")


def render_exchange(exchange: Optional[Dict[str, Any]]) -> str:
    if not exchange:
        return "（本次用例未发出 HTTP 请求）"

    req, resp = exchange["request"], exchange["response"]
    lines = [f"{exchange['method']} {exchange['url']}"]

    for label, key in (("query  ", "params"), ("form   ", "form"),
                       ("json   ", "json"), ("headers", "headers")):
        if req.get(key):
            lines.append(f"{label}: {json.dumps(req[key], ensure_ascii=False)}")
    if req.get("cookies"):
        lines.append(f"cookies: {', '.join(req['cookies'])}")

    lines.append("-" * 60)
    lines.append(f"HTTP {resp['status']}   耗时 {exchange['elapsed_ms']} ms")

    picked = {k: v for k, v in resp.get("headers", {}).items() if k.lower() in INTERESTING_HEADERS}
    if picked:
        lines.append(f"响应头 : {json.dumps(picked, ensure_ascii=False)}")
    lines.append("响应体 :")
    lines.append(resp.get("body", ""))
    return "\n".join(lines)


def render_all(exchanges) -> str:
    """多条请求按发生顺序拼成一段，失败报告里用。"""
    if not exchanges:
        return "（本次用例未发出 HTTP 请求）"
    total = len(exchanges)
    blocks = [
        f"===== 请求 {index + 1}/{total} =====\n{render_exchange(ex)}"
        for index, ex in enumerate(exchanges)
    ]
    return "\n\n".join(blocks)
