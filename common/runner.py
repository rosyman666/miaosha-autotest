# -*- coding: utf-8 -*-
"""执行层：把一条用例数据变成一次请求 + 一次断言。

用例文件里只写 pytest.mark.parametrize + 一行 run_case，具体怎么发、怎么断言、
怎么在报告里分组，都在这里。这样加一个模块 = 加一个 YAML + 复制三行代码。
"""
from typing import Any, Dict

import allure

from common.api_client import ApiClient
from common.expectation import check

# YAML 里的写法 -> requests 的参数名。form 比 data 更像接口文档里的说法
PAYLOAD_MAP = {"params": "params", "form": "data", "json": "json", "headers": "headers"}

SEVERITY = {"blocker": "blocker", "critical": "critical", "normal": "normal",
            "minor": "minor", "trivial": "trivial"}


def apply_allure(case: Dict[str, Any]) -> None:
    """把用例编号、模块、严重级写进 Allure 报告，报告里能按模块/严重级筛。"""
    allure.dynamic.epic("秒杀系统接口自动化")
    allure.dynamic.feature(case.get("module", "未分组"))
    allure.dynamic.story(case["title"])
    allure.dynamic.title(f"{case['id']} {case['title']}")
    allure.dynamic.severity(SEVERITY.get(case.get("severity", "normal"), "normal"))
    if case.get("defect"):
        allure.dynamic.tag("缺陷锁定")
    if case.get("note"):
        allure.dynamic.description(case["note"])


def build_kwargs(request: Dict[str, Any]) -> Dict[str, Any]:
    """从用例的 request 段取出 requests 认识的参数。"""
    kwargs: Dict[str, Any] = {}
    for key, target in PAYLOAD_MAP.items():
        value = request.get(key)
        if value is not None:
            kwargs[target] = value
    return kwargs


def run_request(client: ApiClient, request: Dict[str, Any]) -> Any:
    """按用例里的 request 段发一次请求。"""
    method = str(request["method"]).upper()
    path = request["path"]
    with allure.step(f"{method} {path}"):
        return client.request(method, path, **build_kwargs(request))


def run_case(case: Dict[str, Any], client: ApiClient) -> None:
    """执行一条用例：限流让路 -> 前置请求 -> 主请求 -> 断言。

    pre 用于「必须先让系统进入某个状态」的场景，最典型的是秒杀验证码：
    checkVerifyCode 校验成功即删 Redis key，验证码是一次性的，
    想验证「不传验证码会怎样」，得先重新生成一张。
    """
    request = case["request"]
    rate = case.get("rate_limit") or {}
    if rate:
        client.wait_rate(request["path"].split("?")[0], rate.get("seconds", 5), rate.get("max_count", 5))

    for step in case.get("pre") or []:
        with allure.step(f"前置 {step['method'].upper()} {step['path']}"):
            client.request(str(step["method"]).upper(), step["path"], **build_kwargs(step))

    response = run_request(client, request)
    with allure.step(f"断言 {len(case['expect'])} 项"):
        check(response, case["expect"], case["id"])
