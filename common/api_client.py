# -*- coding: utf-8 -*-
"""请求层：Requests 会话封装。

所有用例不直接 import requests，而是通过 ApiClient 发请求。
好处：换域名、加统一日志、加重试，只改这一个文件。
"""
import requests


class ApiClient:
    """一个 ApiClient = 一个独立会话（自动管理 Cookie）。"""

    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    # ---------- 基础方法 ----------
    def get(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        return self.session.get(self.base_url + path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        return self.session.post(self.base_url + path, **kwargs)

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
