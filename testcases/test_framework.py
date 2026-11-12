# -*- coding: utf-8 -*-
"""框架自检：不连被测服务，验证「用例数据」和「断言引擎」本身没问题。

托管 CI 里没有秒杀系统依赖的 MySQL / Redis / RabbitMQ / 8003 应用，跑不了真接口；
但框架自身必须能被回归 —— YAML 漏字段、断言引擎把 true 当 int、占位符解析丢类型，
这些错如果等到本地跑全量才暴露，排查成本比现在高得多。

    python -m pytest testcases/test_framework.py
"""
import pytest

from common import cases as case_repo
from common.env_loader import load_env
from common.expectation import ExpectationError, check, evaluate
from common.runner import build_kwargs

pytestmark = pytest.mark.framework


class FakeResponse:
    """Response 替身：只实现断言层用到的几个属性。"""

    def __init__(self, status=200, body=None, text=None, headers=None, cookies=None, raw=b""):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.text = text if text is not None else ""
        self.content = raw

    def json(self):
        if self._body is None:
            raise ValueError("响应不是 JSON")
        return self._body


# ------------------------------------------------------------ 断言引擎
def test_all_checks_pass():
    resp = FakeResponse(
        body={"code": 0, "data": {"goods": {"name": "iphoneX", "stock": 12}}},
        headers={"Content-Type": "application/json"},
        cookies={"token": "abc"},
        raw=b"x" * 100,
    )
    problems = evaluate(
        resp,
        {
            "status": 200,
            "json": {"code": 0},
            "json_not": {"code": 1},
            "json_exists": ["data.goods.name"],
            "json_absent": ["data.goods.note"],
            "json_type": {"data.goods.stock": "int", "data.goods.name": "str"},
            "json_matches": {"data.goods.name": "iphone.*"},
            "json_gt": {"data.goods.stock": 10},
            "header_contains": {"Content-Type": "json"},
            "cookie": {"token": "present"},
            "content_length_gt": 50,
        },
    )
    assert problems == []


def test_all_mismatches_are_reported_together():
    """一次收集全部不符项：改一处跑一次太慢，报告里要能一次看到所有偏差。"""
    resp = FakeResponse(body={"code": 10001, "data": None})
    problems = evaluate(resp, {"status": 404, "json": {"code": 0}, "json_exists": ["data.goods"]})
    assert len(problems) == 3
    assert any("status" in p for p in problems)
    assert any("json.code" in p for p in problems)
    assert any("data.goods" in p for p in problems)


def test_missing_json_path_is_reported_not_crashed():
    problems = evaluate(FakeResponse(body={"code": 0}), {"json": {"data.a.b": 1}})
    assert len(problems) == 1
    assert "路径不存在" in problems[0]


def test_non_json_response_does_not_raise():
    """商品列表页返回 HTML，断言层不能因为 .json() 抛错就崩掉。"""
    problems = evaluate(FakeResponse(body=None), {"json": {"code": 0}})
    assert len(problems) == 1


def test_json_path_supports_list_index():
    resp = FakeResponse(body={"data": [{"id": 7}]})
    assert evaluate(resp, {"json": {"data.0.id": 7}}) == []
    assert evaluate(resp, {"json": {"data.9.id": 7}})


def test_bool_is_not_accepted_as_int():
    """Python 里 bool 是 int 的子类，不单独判断的话 true 会冒充 1 通过类型断言。"""
    resp = FakeResponse(body={"flag": True})
    problems = evaluate(resp, {"json_type": {"flag": "int"}})
    assert len(problems) == 1 and "bool" in problems[0]
    assert evaluate(resp, {"json_type": {"flag": "bool"}}) == []


def test_number_accepts_int_and_float():
    assert evaluate(FakeResponse(body={"p": 9.9}), {"json_type": {"p": "number"}}) == []
    assert evaluate(FakeResponse(body={"p": 9}), {"json_type": {"p": "number"}}) == []
    assert evaluate(FakeResponse(body={"p": "9"}), {"json_type": {"p": "number"}})


def test_cookie_absent():
    problems = evaluate(FakeResponse(cookies={}), {"cookie": {"token": "absent"}})
    assert problems == []
    problems = evaluate(FakeResponse(cookies={"token": "x"}), {"cookie": {"token": "absent"}})
    assert len(problems) == 1


def test_check_raises_with_case_id_and_problems():
    with pytest.raises(ExpectationError) as err:
        check(FakeResponse(body={"code": 30010}), {"json": {"code": 0}}, "LOGIN-999")
    message = str(err.value)
    assert "LOGIN-999" in message and "30010" in message


def test_unknown_keyword_is_flagged():
    """写错断言关键字不能被静默忽略，否则用例看起来"过了"其实什么都没验。"""
    problems = evaluate(FakeResponse(body={"code": 0}), {"json_cod": 0})
    assert len(problems) == 1 and "未知断言关键字" in problems[0]


# ------------------------------------------------------------ 用例数据
def test_placeholder_keeps_original_type():
    ctx = {"goods_id": 1, "user": {"mobile": "130"}}
    assert case_repo.resolve("${goods_id}", {"goods_id": 1}) == 1
    assert case_repo.resolve("/goods/detail/${goods_id}", ctx) == "/goods/detail/1"
    assert case_repo.resolve({"m": "${user.mobile}"}, {"user.mobile": "130"}) == {"m": "130"}


def test_undefined_placeholder_raises():
    with pytest.raises(KeyError):
        case_repo.resolve("${nope}", {})


def test_all_case_files_are_valid():
    env = load_env()
    total = 0
    for path in case_repo.case_files():
        module = path.rsplit(".", 1)[0]
        loaded = case_repo.load_cases(module, env)
        assert loaded, f"{path} 里没有用例"
        assert case_repo.validate(loaded) == [], f"{path} 结构校验未通过"
        total += len(loaded)
    assert total >= 30, f"用例总数 {total}，低于预期"


def test_case_ids_are_unique_across_modules():
    env = load_env()
    ids = []
    for path in case_repo.case_files():
        ids += [c["id"] for c in case_repo.load_cases(path.rsplit(".", 1)[0], env)]
    assert len(ids) == len(set(ids)), "用例编号有重复"


def test_validate_catches_missing_field():
    problems = case_repo.validate([{"id": "X-001", "title": "缺 request 与 expect"}])
    assert any("request" in p for p in problems)
    assert any("expect" in p for p in problems)


def test_build_kwargs_maps_form_to_data():
    kwargs = build_kwargs({"method": "post", "path": "/x", "form": {"a": 1}, "headers": {"H": "v"}})
    assert kwargs == {"data": {"a": 1}, "headers": {"H": "v"}}
