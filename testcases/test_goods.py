# -*- coding: utf-8 -*-
"""商品模块用例。"""


def test_goods_list(client):
    """商品列表页可访问且返回非空页面。"""
    resp = client.get("/goods/to_list")
    assert resp.status_code == 200
    assert resp.text.strip(), "商品列表页不应为空"


def test_goods_detail(client, goods_id):
    """商品详情 -> code=0，data 含 goodsName。"""
    resp = client.get(f"/goods/detail/{goods_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0, f"查询在售商品应成功: {body}"
    assert body["data"]["goods"]["goodsName"], "详情应包含 goods.goodsName"


def test_goods_detail_not_exist(client):
    """[缺陷锁定] 查询不存在商品 -> 当前实际返回 10001(系统异常)。

    正确行为应返回明确的业务提示（如商品不存在），
    而不是把未处理的空指针兜底成"系统异常"。
    """
    resp = client.get("/goods/detail/99999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 10001, (
        f"缺陷已被修复？实际返回 {body['code']}，请更新断言"
    )
