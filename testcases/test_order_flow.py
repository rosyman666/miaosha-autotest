# -*- coding: utf-8 -*-
"""会改变系统状态的用例：完整下单链路、限流触发。

单独成一个文件并打 miaosha_write 标记，是因为它们会消耗库存、占满限流窗口，
和只读回归混在一起跑会互相影响：前一条把库存打空，后一条拿到的 path 判定就变了。

跑之前先把数据重置回基线：
    python -m tools seed --stock 10
    python -m pytest -m miaosha_write
"""
import time

import pytest

from common.expectation import check

pytestmark = pytest.mark.miaosha_write


def test_full_order_flow(client, goods_id):
    """完整秒杀链路：出验证码 -> 换令牌 -> 下单 -> 轮询订单号。

    验证码是一次性的（checkVerifyCode 校验成功即删 Redis key），
    所以下单前必须重新生成一次，不能复用前面用例的那张图。
    """
    client.wait_rate("/miaosha/path", 5, 5)

    # 前置基线：seed 之后应当没有订单，result 返回 0（排队中）
    before = client.get(f"/miaosha/result?goodsId={goods_id}").json()
    assert before["data"] == 0, f"seed 后应无订单，result 期望 0，实际 {before}"

    check(
        client.get(f"/miaosha/verifyCode?goodsId={goods_id}"),
        {"status": 200, "content_length_gt": 1000},
        "生成验证码",
    )

    token_resp = client.get(f"/miaosha/path?goodsId={goods_id}&verifyCode=0")
    check(token_resp, {"status": 200, "json": {"code": 0}, "json_exists": ["data"]}, "换取秒杀令牌")
    path = token_resp.json()["data"]

    order_resp = client.post(f"/miaosha/{path}/do_miaosha?goodsId={goods_id}")
    check(order_resp, {"status": 200, "json": {"code": 0}}, "提交秒杀请求")

    # 下单是异步的：接口返回成功只代表消息进了队列，订单号要靠 result 轮询
    order_id = 0
    for _ in range(20):
        result = client.get(f"/miaosha/result?goodsId={goods_id}").json()
        order_id = result.get("data", 0)
        if order_id and order_id > 0:
            break
        time.sleep(0.5)
    assert order_id and order_id > 0, f"10 秒内未拿到订单号，最后结果: {order_id}"


def test_access_limit_returns_30002(client, goods_id):
    """连打同一接口触发 @AccessLimit(5 秒 5 次)，第 6 次被限流。

    选 /miaosha/result 而不是 /miaosha/path：验证码是一次性消费的，
    path 接口从第 2 次起就会因为「验证码已失效」返回 30004，测不出限流。
    result 只读、每次返回同样的排队状态，适合用来打满窗口。

    这条同时钉住枚举文案错位：限流返回 30002 ACCESS_LIMIT_REACHED，文案却是「请求非法!」；
    而真正「请求非法」的场景（验证码错误）返回 30004，文案是「访问太频繁!」。
    两个枚举的编号、名字、文案正好互为颠倒，这里把现状固定下来。
    """
    # 限流计数在服务端 Redis 的 AccessKey 里，客户端查不到也改不了，只能等窗口过期
    time.sleep(5.2)

    codes, last_body = [], None
    for _ in range(6):
        last_body = client.get(f"/miaosha/result?goodsId={goods_id}").json()
        codes.append(last_body["code"])

    assert codes[:5] == [0] * 5, f"限流窗口内前 5 次应放行，实际 {codes}"
    assert codes[5] == 30002, f"第 6 次应返回 30002，实际 {codes[5]}（{last_body}）"
    assert last_body["message"] == "请求非法!", (
        f"限流提示文案变了：{last_body['message']}；若已改为「访问太频繁」说明缺陷已修复"
    )
