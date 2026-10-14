# -*- coding: utf-8 -*-
"""秒杀模块用例。

读操作用例默认全量跑；真正下单的写操作用例打上 miaosha_write 标记，
常规回归排除（pytest.ini 已配置 marker），避免污染库存数据。
"""
import time

import pytest


def test_verify_code(client, goods_id):
    """验证码接口可访问且返回图片内容。"""
    resp = client.get(f"/miaosha/verifyCode?goodsId={goods_id}")
    assert resp.status_code == 200
    assert len(resp.content) > 0, "验证码不应为空响应"


def test_path_wrong_verifycode(client, goods_id):
    """错误验证码 -> path 接口拒绝下发秒杀地址。"""
    resp = client.get(f"/miaosha/path?goodsId={goods_id}&verifyCode=999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] != 0, "错误验证码不应拿到秒杀 path"


def test_path_verifycode_zero(client, goods_id):
    """[缺陷锁定] verifyCode=0 可以通过校验。

    根因：JDK 17 移除 Nashorn 后，验证码算式计算抛 NPE 被 catch 吞掉、
    返回 0 写进 Redis，导致"正确答案恒为 0"，校验形同虚设。
    这条用例通过 == 缺陷仍存在；项目修复后本用例会失败，属预期。
    """
    resp = client.get(f"/miaosha/path?goodsId={goods_id}&verifyCode=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0 and body["data"], (
        "缺陷已被修复（0 不再是正确答案），请把本用例改为断言 code!=0"
    )


def test_miaosha_result(client, goods_id):
    """秒杀结果轮询接口 -> 业务码 0（data 为 0=排队中/订单id/-1=失败）。"""
    resp = client.get(f"/miaosha/result?goodsId={goods_id}")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


@pytest.mark.miaosha_write
def test_miaosha_order_flow(client, goods_id):
    """完整秒杀下单链路（写操作，单独执行）：取 path -> 下单 -> 轮询订单号。

    跑之前需重置数据：
      UPDATE miaosha_goods SET stock_count=10 WHERE goods_id=1;
      redis-cli set GoodsKey:gs1 10
    """
    # 0. 秒杀接口有 @AccessLimit(5秒5次) 限流，先等限流窗口重置
    time.sleep(6)

    # 1. 生成验证码。验证码是一次性的（checkVerifyCode 校验成功即删 Redis key），
    #    所以下单前必须重新生成；又因 Nashorn 缺陷，正确答案恒为 0
    r0 = client.get(f"/miaosha/verifyCode?goodsId={goods_id}")
    assert r0.status_code == 200

    # 2. 取秒杀 path（verifyCode=0 过校验，正是静默缺陷的实证）
    r1 = client.get(f"/miaosha/path?goodsId={goods_id}&verifyCode=0").json()
    assert r1["code"] == 0, f"取秒杀 path 失败: {r1}"
    path = r1["data"]

    # 3. 下单
    r2 = client.post(f"/miaosha/{path}/do_miaosha?goodsId={goods_id}").json()
    assert r2["code"] == 0, f"下单请求失败: {r2}"

    # 4. 异步下单，轮询结果（最多 10 秒）
    order_id = 0
    for _ in range(20):
        r3 = client.get(f"/miaosha/result?goodsId={goods_id}").json()
        order_id = r3.get("data", 0)
        if order_id and order_id > 0:
            break
        time.sleep(0.5)
    assert order_id and order_id > 0, f"10 秒内未拿到订单号，最后结果: {order_id}"
