# -*- coding: utf-8 -*-
"""用例数据层：从 data/cases/*.yaml 读用例，解析占位符，做结构校验。

为什么要单独一层：
    加用例不改 Python —— 新的边界值、新的错误码，改 YAML 就能跑；
    用例编号、严重级、断言都跟着数据走，报告里能直接看出覆盖了哪些场景。

占位符 ${xxx} 从环境配置里取（${user.mobile}、${goods_id}、${base_url}），
整串就是一个占位符时保留原类型，避免 goods_id 被写成字符串 "1"。
"""
import os
import re
from typing import Any, Dict, List

import yaml

from common.expectation import SUPPORTED_KEYS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(BASE, "data", "cases")

_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")
_REQUIRED = ("id", "title", "request", "expect")
_METHODS = ("get", "post", "put", "delete")

_cache: Dict[str, List[dict]] = {}


def _flatten(data: dict, prefix: str = "") -> Dict[str, Any]:
    """把 env 嵌套字典拍平成 a.b.c -> 值，供占位符按名取用。"""
    flat: Dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, name + "."))
        else:
            flat[name] = value
    return flat


def resolve(value: Any, context: Dict[str, Any]) -> Any:
    """递归替换 ${...}；整串即占位符时返回原值，保留 int/bool 类型。"""
    if isinstance(value, str):
        whole = _PLACEHOLDER.fullmatch(value)
        if whole:
            key = whole.group(1)
            if key not in context:
                raise KeyError(f"用例里引用了未定义的占位符 ${{{key}}}")
            return context[key]
        return _PLACEHOLDER.sub(lambda m: str(context[m.group(1)]), value)
    if isinstance(value, dict):
        return {k: resolve(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, context) for v in value]
    return value


def case_files() -> List[str]:
    if not os.path.isdir(CASES_DIR):
        return []
    return sorted(f for f in os.listdir(CASES_DIR) if f.endswith((".yaml", ".yml")))


def load_cases(module: str, env: dict | None = None) -> List[dict]:
    """读取某个模块的用例集并解析占位符（结果缓存，同一进程只读一次盘）。"""
    if module in _cache:
        return _cache[module]

    path = os.path.join(CASES_DIR, f"{module}.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"用例数据文件不存在: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    context = _flatten(env) if env else {}
    cases: List[dict] = []
    for case in raw.get("cases") or []:
        item = dict(case)
        item["module"] = raw.get("module") or module
        item.setdefault("severity", "normal")
        item.setdefault("auth", True)
        cases.append(resolve(item, context))

    problems = validate(cases)
    if problems:
        raise ValueError(f"{path} 用例数据有问题:\n" + "\n".join(f"  - {p}" for p in problems))

    _cache[module] = cases
    return cases


def validate(cases: List[dict]) -> List[str]:
    """结构校验：CI 里不连被测服务也能跑，防止改 YAML 时漏字段。"""
    problems: List[str] = []
    seen = set()
    for index, case in enumerate(cases):
        label = case.get("id") or f"第 {index + 1} 条"
        for key in _REQUIRED:
            if not case.get(key):
                problems.append(f"{label}: 缺少必填字段 {key}")
        if case.get("id") in seen:
            problems.append(f"{label}: 用例编号重复")
        seen.add(case.get("id"))

        request = case.get("request") or {}
        method = str(request.get("method", "")).lower()
        if method not in _METHODS:
            problems.append(f"{label}: method 必须是 {_METHODS}，实际 {method!r}")
        if not str(request.get("path", "")).startswith("/"):
            problems.append(f"{label}: path 必须以 / 开头，实际 {request.get('path')!r}")

        expect = case.get("expect") or {}
        if not isinstance(expect, dict) or not expect:
            problems.append(f"{label}: expect 不能为空")
        else:
            for key in expect:
                if key not in SUPPORTED_KEYS:
                    problems.append(f"{label}: expect 里有不支持的断言 {key!r}")

        if case.get("severity") not in ("blocker", "critical", "normal", "minor", "trivial"):
            problems.append(f"{label}: severity 取值非法 {case.get('severity')!r}")

        payloads = {"params", "form", "json"} & set(request)
        if len(payloads) > 1:
            problems.append(f"{label}: params/form/json 只能出现一个，实际 {sorted(payloads)}")

        for index, step in enumerate(case.get("pre") or []):
            prefix = f"{label} 的第 {index + 1} 个前置请求"
            if str(step.get("method", "")).lower() not in _METHODS:
                problems.append(f"{prefix}: method 非法 {step.get('method')!r}")
            if not str(step.get("path", "")).startswith("/"):
                problems.append(f"{prefix}: path 必须以 / 开头")
    return problems
