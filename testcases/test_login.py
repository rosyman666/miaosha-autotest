# -*- coding: utf-8 -*-
"""登录模块用例。"""
from common.api_client import ApiClient


def test_login_success(env):
    """正常账号 + 正确密文 -> code=0，并下发 token Cookie。"""
    c = ApiClient(env["base_url"])
    user = env["user"]
    resp = c.login(user["mobile"], user["password_cipher"])
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert c.token, "登录成功应下发 token Cookie"


def test_login_wrong_password(env):
    """错误密码密文 -> 业务码 30010（密码错误），不发放 token。"""
    c = ApiClient(env["base_url"])
    user = env["user"]
    wrong_cipher = "0" * 32  # 位数合法但内容错误
    resp = c.login(user["mobile"], wrong_cipher)
    assert resp.status_code == 200
    assert resp.json()["code"] == 30010
    assert not c.token


def test_login_invalid_mobile(env):
    """[缺陷锁定] 非法手机号 -> 当前实际返回 30005(会话错误)。

    正确行为应为 30001(参数绑定错误 BIND_ERROR)。
    根因：GlobleExceptionHandler 把 BindException 映射成了 SESSION_ERROR。
    用例按"当前真实行为"断言，钉住这个缺陷；项目修复后本用例会失败，
    届时把断言改成 30001 即完成回归确认。
    """
    c = ApiClient(env["base_url"])
    user = env["user"]
    resp = c.login("12345", user["password_cipher"])
    assert resp.status_code == 200
    body = resp.json()
    # 修复前：30005；修复后应改为 30001
    assert body["code"] == 30005, (
        f"缺陷已被修复？实际返回 {body['code']}，请更新本用例断言为正确业务码"
    )
