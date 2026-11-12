# -*- coding: utf-8 -*-
"""doctor：跑用例之前先确认依赖是否齐全。

覆盖四层：MySQL（库表数据）、Redis（库存 key）、应用（HTTP 可达）、RabbitMQ（端口）。
任一必需项不通过时，命令以非 0 退出码结束，可直接用于部署检查。

注意：请求用 trust_env=False，绕过系统代理。
本机装了代理软件时，走代理访问 localhost:8003 会拿到 502，
看起来像"应用挂了"，实际是代理把请求转走了。
"""
import socket
from urllib.parse import urlparse

import requests

from tools.settings import Settings
from tools.storage import Cache, MySQL, RedisKeys

REQUIRED_TABLES = ("miaosha_goods", "miaosha_order", "order_info", "miaosha_user")

OK = "[ OK ]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"


def _check_mysql(s: Settings, report: list) -> None:
    try:
        with MySQL(s.db) as db:
            db.query("SELECT 1")
            report.append((OK, "MySQL 连接", s.db.dsn))
            missing = [t for t in REQUIRED_TABLES if not db.table_exists(t)]
            if missing:
                report.append((FAIL, "MySQL 表结构", f"缺少表：{', '.join(missing)}"))
            else:
                report.append((OK, "MySQL 表结构", f"{len(REQUIRED_TABLES)} 张关键表齐全"))
            goods = db.query(
                "SELECT goods_id, stock_count FROM miaosha_goods WHERE goods_id=%s",
                (s.goods_id,),
            )
            if not goods:
                report.append((FAIL, "商品数据", f"miaosha_goods 里没有 goods_id={s.goods_id}"))
            else:
                report.append(
                    (OK, "商品数据", f"goods_id={s.goods_id}，DB 库存 {goods[0]['stock_count']}")
                )
    except Exception as exc:  # noqa: BLE001 - 诊断命令要把原始错误显示出来
        report.append((FAIL, "MySQL 连接", f"{s.db.dsn} -> {exc}"))


def _check_redis(s: Settings, report: list) -> None:
    try:
        with Cache(s.redis) as cache:
            report.append((OK, "Redis 连接", s.redis.dsn))
            key = RedisKeys.stock(s.goods_id)
            stock = cache.get_int(key)
            if stock is None:
                report.append(
                    (FAIL, "库存缓存", f"{key} 不存在，秒杀接口会因库存为空直接返回失败")
                )
            else:
                report.append((OK, "库存缓存", f"{key} = {stock}"))
    except Exception as exc:  # noqa: BLE001
        report.append((FAIL, "Redis 连接", f"{s.redis.dsn} -> {exc}"))


def _check_app(s: Settings, report: list) -> None:
    session = requests.Session()
    session.trust_env = False  # 不走系统代理
    try:
        resp = session.get(f"{s.base_url}/goods/to_list", timeout=5)
        if resp.status_code == 200:
            report.append((OK, "被测应用", f"{s.base_url} 可访问"))
        else:
            report.append((FAIL, "被测应用", f"HTTP {resp.status_code}"))
    except Exception as exc:  # noqa: BLE001
        report.append((FAIL, "被测应用", f"{s.base_url} 不可达 -> {exc}"))
    finally:
        session.close()


def _check_rabbitmq(s: Settings, report: list) -> None:
    """RabbitMQ 只在执行写操作用例时需要，缺失只提示不判失败。"""
    host = urlparse(s.base_url).hostname or "127.0.0.1"
    try:
        with socket.create_connection((host, 5672), timeout=3):
            report.append((OK, "RabbitMQ", f"{host}:5672 可连接"))
    except OSError:
        report.append(
            (SKIP, "RabbitMQ", "5672 未监听：只读用例不受影响，下单用例会失败")
        )


def run(s: Settings) -> int:
    report: list = []
    _check_mysql(s, report)
    _check_redis(s, report)
    _check_app(s, report)
    _check_rabbitmq(s, report)

    width = max(len(name) for _, name, _ in report)
    print("\n环境自检")
    print("-" * 68)
    for status, name, detail in report:
        print(f"{status} {name.ljust(width)}  {detail}")
    print("-" * 68)

    failed = [name for status, name, _ in report if status == FAIL]
    if failed:
        print(f"不通过 {len(failed)} 项：{', '.join(failed)}")
        return 1
    print("全部通过，可以跑常规回归")
    return 0
