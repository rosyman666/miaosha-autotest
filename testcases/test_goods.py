# -*- coding: utf-8 -*-
"""商品模块。用例数据见 data/cases/goods.yaml。"""
import pytest

from common.cases import load_cases
from common.env_loader import load_env
from common.runner import apply_allure, run_case

CASES = load_cases("goods", load_env())


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_goods(case, client, anon_client):
    apply_allure(case)
    run_case(case, client if case["auth"] else anon_client)
