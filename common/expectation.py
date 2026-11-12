# -*- coding: utf-8 -*-
"""断言层：把「期望」写成数据，由这里统一判定。

用例数据里 expect 是一组键值声明，不在 YAML 里写代码，也不写 lambda：
    expect:
      status: 200
      json:
        code: 0
      json_exists: [data.goods.goodsName]
      cookie: {token: present}

一次收集全部不符项再抛错，而不是遇到第一个就中断 —— 接口一条用例常常
同时校验状态码、业务码、关键字段，逐个报错会把「改了三次才跑通」变成日常。
"""
import re
from typing import Any, Dict, List, Tuple

# 支持的关键字 -> 说明（供 test_framework.py 校验用例数据时复用）
SUPPORTED_KEYS = {
    "status": "HTTP 状态码相等",
    "json": "响应 JSON 按点路径取值后相等",
    "json_not": "响应 JSON 按点路径取值后不等",
    "json_in": "响应 JSON 取值属于给定集合",
    "json_exists": "响应 JSON 路径存在且非空",
    "json_absent": "响应 JSON 路径缺失或为空",
    "json_type": "响应 JSON 取值的类型（int/float/number/str/bool/list/dict）",
    "json_matches": "响应 JSON 取值能完整匹配给定正则",
    "json_gt": "响应 JSON 取值大于给定值",
    "json_ge": "响应 JSON 取值大于等于给定值",
    "json_lt": "响应 JSON 取值小于给定值",
    "text_contains": "响应原文包含给定子串（可传列表，全部包含）",
    "header_contains": "响应头包含给定子串（可传 dict）",
    "cookie": "Cookie 存在性：present / absent",
    "content_length_gt": "响应体长度大于给定值",
}

_TYPE_MAP = {
    "int": int,
    "float": float,
    "number": (int, float),
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
}


class ExpectationError(AssertionError):
    """断言失败。消息里带用例编号和实际值，报告里能直接定位。"""


def _walk(obj: Any, path: str) -> Tuple[bool, Any]:
    """按 a.b.c 取值；返回 (是否存在, 值)。数字段视为列表下标。"""
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return False, None
            cur = cur[part]
        elif isinstance(cur, list):
            if not part.lstrip("-").isdigit():
                return False, None
            idx = int(part)
            if not -len(cur) <= idx < len(cur):
                return False, None
            cur = cur[idx]
        else:
            return False, None
    return True, cur


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _type_name(value: Any) -> str:
    """bool 要排在 int 前面判断：Python 里 bool 是 int 的子类，true 会被当成 int。"""
    if isinstance(value, bool):
        return "bool"
    for name in ("int", "float", "str", "list", "dict"):
        if isinstance(value, _TYPE_MAP[name]):
            return name
    return type(value).__name__


def _json_of(response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _show(value: Any, limit: int = 80) -> str:
    """把实际值压成一行，避免把整段 HTML 塞进失败消息。"""
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def evaluate(response, expect: Dict[str, Any]) -> List[str]:
    """返回全部不符项的描述列表；空列表表示通过。"""
    problems: List[str] = []
    body_cache = {}

    def body():
        if "v" not in body_cache:
            body_cache["v"] = _json_of(response)
        return body_cache["v"]

    unknown = [k for k in expect if k not in SUPPORTED_KEYS]
    if unknown:
        problems.append(f"未知断言关键字 {unknown}，支持的有 {sorted(SUPPORTED_KEYS)}")

    # ---- HTTP 状态码 ----
    if "status" in expect and response.status_code != expect["status"]:
        problems.append(f"status: 期望 {expect['status']}，实际 {response.status_code}")

    # ---- JSON 等值 / 不等 / 集合 ----
    if "json" in expect:
        data = body()
        for path, want in expect["json"].items():
            ok, got = _walk(data, path)
            if not ok:
                problems.append(f"json.{path}: 路径不存在（响应可能不是 JSON）")
            elif got != want:
                problems.append(f"json.{path}: 期望 {want!r}，实际 {got!r}")

    if "json_not" in expect:
        data = body()
        for path, unwanted in expect["json_not"].items():
            ok, got = _walk(data, path)
            if ok and got == unwanted:
                problems.append(f"json.{path}: 期望不等于 {unwanted!r}，实际相同")

    if "json_in" in expect:
        data = body()
        for path, candidates in expect["json_in"].items():
            ok, got = _walk(data, path)
            if not ok:
                problems.append(f"json.{path}: 路径不存在")
            elif got not in candidates:
                problems.append(f"json.{path}: 期望属于 {candidates}，实际 {got!r}")

    # ---- 存在性 ----
    for path in expect.get("json_exists", []):
        ok, got = _walk(body(), path)
        if not ok or _is_empty(got):
            problems.append(f"json.{path}: 期望存在且非空，实际 {_show(got) if ok else '缺失'}")

    for path in expect.get("json_absent", []):
        ok, got = _walk(body(), path)
        if ok and not _is_empty(got):
            problems.append(f"json.{path}: 期望缺失或为空，实际 {_show(got)}")

    # ---- 类型 ----
    for path, type_name in expect.get("json_type", {}).items():
        if type_name not in _TYPE_MAP:
            problems.append(f"json_type.{path}: 不支持的类型名 {type_name!r}")
            continue
        ok, got = _walk(body(), path)
        if not ok:
            problems.append(f"json.{path}: 路径不存在")
            continue
        actual = _type_name(got)
        allowed = {"number": ("int", "float")}.get(type_name, (type_name,))
        if actual not in allowed:
            problems.append(f"json.{path}: 期望类型 {type_name}，实际 {actual}（{_show(got)}）")

    # ---- 正则 ----
    for path, pattern in expect.get("json_matches", {}).items():
        ok, got = _walk(body(), path)
        if not ok:
            problems.append(f"json.{path}: 路径不存在")
        elif not isinstance(got, str):
            problems.append(f"json.{path}: 期望是字符串才能做正则，实际 {type(got).__name__}")
        elif not re.fullmatch(pattern, got):
            problems.append(f"json.{path}: 期望匹配 /{pattern}/，实际 {_show(got)}")

    # ---- 数值比较 ----
    for key, symbol, judge in (
        ("json_gt", ">", lambda a, b: a > b),
        ("json_ge", ">=", lambda a, b: a >= b),
        ("json_lt", "<", lambda a, b: a < b),
    ):
        for path, threshold in expect.get(key, {}).items():
            ok, got = _walk(body(), path)
            if not ok:
                problems.append(f"json.{path}: 路径不存在")
            elif isinstance(got, bool) or not isinstance(got, (int, float)):
                problems.append(f"json.{path}: 期望是数字，实际 {type(got).__name__}（{_show(got)}）")
            elif not judge(got, threshold):
                problems.append(f"json.{path}: 期望 {symbol} {threshold}，实际 {got}")

    # ---- 响应原文 ----
    wanted_text = expect.get("text_contains")
    if wanted_text:
        needles = [wanted_text] if isinstance(wanted_text, str) else list(wanted_text)
        text = response.text or ""
        for needle in needles:
            if needle not in text:
                problems.append(f"text: 期望包含 {needle!r}，实际未出现（长度 {len(text)}）")

    # ---- 响应头 / Cookie ----
    for name, needle in (expect.get("header_contains") or {}).items():
        actual = response.headers.get(name, "")
        if needle not in actual:
            problems.append(f"header.{name}: 期望包含 {needle!r}，实际 {actual!r}")

    for name, state in (expect.get("cookie") or {}).items():
        present = bool(response.cookies.get(name))
        if state == "present" and not present:
            problems.append(f"cookie.{name}: 期望下发，实际未下发")
        elif state == "absent" and present:
            problems.append(f"cookie.{name}: 期望不下发，实际下发了")

    if "content_length_gt" in expect:
        size = len(response.content or b"")
        if size <= expect["content_length_gt"]:
            problems.append(f"content_length: 期望 > {expect['content_length_gt']}，实际 {size}")

    return problems


def check(response, expect: Dict[str, Any], label: str = "") -> None:
    """断言入口：不符项非空则抛 ExpectationError。"""
    problems = evaluate(response, expect)
    if problems:
        head = f"{label} 期望不满足（{len(problems)} 项）" if label else f"期望不满足（{len(problems)} 项）"
        raise ExpectationError(head + "\n" + "\n".join(f"  - {p}" for p in problems))
