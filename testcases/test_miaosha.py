# -*- coding: utf-8 -*-
"""秒杀模块。用例数据见 data/cases/miaosha.yaml。

这里只有只读用例；真正下单的链路在 test_order_flow.py，打了 miaosha_write 标记，
常规回归默认排除。
"""
import pytest

from common.cases import load_cases
from common.env_loader import load_env
from common.runner import apply_allure, run_case

CASES = load_cases("miaosha", load_env())


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_miaosha(case, client, anon_client):
    apply_allure(case)
    run_case(case, client if case["auth"] else anon_client)
