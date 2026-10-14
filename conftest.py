# -*- coding: utf-8 -*-
"""全局 fixture：整个测试会话只登录一次，所有用例复用登录态。"""
import pytest

from common.api_client import ApiClient
from common.env_loader import load_env


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


@pytest.fixture(scope="session")
def goods_id(env) -> int:
    return env["goods_id"]
