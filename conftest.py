# -*- coding: utf-8 -*-
"""全局 fixture 与报告钩子。

    env          环境配置（整个会话读一次盘）
    client       已登录会话，整个会话复用（登录接口只打一次）
    anon_client  未登录会话，每个用例一个，用来验证「没登录会怎样」
    钩子         用例失败时，把本次请求/响应挂进 Allure 和 pytest-html 报告
"""
import os
import platform
import sys
import time

import pytest

from common.api_client import ApiClient
from common.env_loader import load_env
from common.reporting import render_all

BASE = os.path.dirname(os.path.abspath(__file__))
ALLURE_DIR = os.path.join(BASE, "allure-results")


@pytest.fixture(scope="session")
def env() -> dict:
    return load_env()


@pytest.fixture(scope="session")
def client(env) -> ApiClient:
    """已登录的客户端：登录一次，后续所有用例自动带 token Cookie。"""
    c = ApiClient(env["base_url"])
    user = env["user"]
    resp = c.login(user["mobile"], user["password_cipher"])
    assert resp.status_code == 200, f"登录接口 HTTP 异常: {resp.status_code}"
    body = resp.json()
    assert body["code"] == 0, f"登录失败: {body}"
    assert c.token, "登录成功但未拿到 token Cookie"
    return c


@pytest.fixture
def anon_client(env) -> ApiClient:
    """未登录会话：断言「未登录」相关行为时必须用干净的 Cookie 容器。

    不能复用 client —— 它带着登录态，断言「未登录被拦截」永远不会成立。
    """
    return ApiClient(env["base_url"])


@pytest.fixture(scope="session")
def goods_id(env) -> int:
    return env["goods_id"]


@pytest.fixture(scope="session")
def case_env(env) -> dict:
    """给用例数据做占位符解析用的扁平上下文，例如 ${user.mobile}。"""
    return env


# ---------------------------------------------------------------- 报告钩子
_CASE_START: dict = {}


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    """记下每条用例真正开始执行的时刻。

    client 是 session 级、全程复用，它的 exchanges 里存着前面几十条用例的请求。
    报告只该展示本条用例发出的请求，所以按时间戳切片，而不是一律取最后 N 条。
    挂在 call 阶段（而不是 setup）：setup 阶段还在建 fixture，登录请求属于「前置」，
    不该混进用例自己的请求里。
    """
    _CASE_START[item.nodeid] = time.time()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """用例失败时自动附上本次发出的 HTTP 请求/响应。

    排查接口用例最费时间的不是断言本身，而是「它到底发了什么、服务返回了什么」。
    失败现场直接贴在报告里，不用再复跑一遍加 print。
    """
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return

    start = _CASE_START.get(item.nodeid, 0)
    exchanges = []
    for name in ("client", "anon_client"):
        client = item.funcargs.get(name)
        if isinstance(client, ApiClient):
            exchanges.extend(ex for ex in client.exchanges if ex["ts"] >= start)
    if not exchanges:
        return

    text = render_all(exchanges[-5:])

    # pytest-html 会把 section 内容整段 escape 后放进 <pre>，所以这里给纯文本即可。
    # 注意不能用 item.add_report_section：它在 makereport 之后才写入 item，
    # 当前这份 report 已经生成完了，加进去不会渲染。
    report.sections.append(("HTTP 请求/响应", text))

    try:
        import allure

        allure.attach(text, name="HTTP 请求/响应", attachment_type=allure.attachment_type.TEXT)
    except Exception:  # 没装 allure 或不在 allure 运行时，忽略
        pass


# ---------------------------------------------------------- Allure 环境信息
def pytest_sessionfinish(session, exitstatus):
    """写 Allure 的环境信息，报告首页能看到跑的是哪套环境。"""
    if not os.path.isdir(ALLURE_DIR):
        return
    env = load_env()
    lines = [
        f"被测环境={env['base_url']}",
        f"商品ID={env['goods_id']}",
        f"Python={platform.python_version()}",
        f"操作系统={platform.system()} {platform.release()}",
        f"解释器={sys.executable}",
    ]
    with open(os.path.join(ALLURE_DIR, "environment.properties"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    categories = os.path.join(BASE, "docs", "allure", "categories.json")
    if os.path.exists(categories):
        import shutil

        shutil.copyfile(categories, os.path.join(ALLURE_DIR, "categories.json"))
