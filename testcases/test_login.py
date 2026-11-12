# -*- coding: utf-8 -*-
"""登录模块。

用例本身在 data/cases/login.yaml，这里只做驱动：加一条登录场景改 YAML，不动这个文件。
auth=false 的用例走 anon_client（干净会话），否则走 session 级已登录的 client。
"""
import pytest

from common.cases import load_cases
from common.env_loader import load_env
from common.runner import apply_allure, run_case

CASES = load_cases("login", load_env())


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_login(case, client, anon_client):
    apply_allure(case)
    run_case(case, client if case["auth"] else anon_client)
