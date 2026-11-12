# -*- coding: utf-8 -*-
"""reconcile：对账 MySQL 与 Redis，找出缓存和数据库不一致的地方。

秒杀系统的库存与订单状态同时存在两处：
    MySQL  miaosha_goods.stock_count / miaosha_order
    Redis  GoodsKey:gs{n}          库存预减
           OrderKey:moug{uid}_{n}  下单标记（防重复下单）

正常情况下这两处应当同向变化。一旦出现"只扣缓存不写库"（消息投递失败不回滚）
或"只写库不清缓存"，接口看起来都是成功的，只有对账能发现。

检查项：
    1. 库存一致      DB stock_count 与 Redis 库存是否相同
    2. 售罄标记      Redis 标记售罄但 DB 仍有库存（或反之）
    3. 幽灵订单      缓存标记了已下单，数据库查不到订单
    4. 漏缓存        数据库有订单，缓存里查不到标记
退出码：无差异 0，有差异 1。
"""
from dataclasses import dataclass, field
from typing import Dict, List

from tools.settings import Settings
from tools.storage import Cache, MySQL, RedisKeys

OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"

ORDER_PREFIX = "OrderKey:moug"


@dataclass
class DbOrder:
    order_id: int
    user_id: str
    nickname: str


@dataclass
class Finding:
    level: str
    item: str
    detail: str


@dataclass
class Report:
    findings: List[Finding] = field(default_factory=list)

    def add(self, level: str, item: str, detail: str) -> None:
        self.findings.append(Finding(level, item, detail))

    @property
    def failed(self) -> int:
        return sum(1 for f in self.findings if f.level == FAIL)

    def render(self, goods_id: int) -> str:
        width = max(len(f.item) for f in self.findings)
        lines = [f"\n对账结果  goods_id={goods_id}", "-" * 68]
        for f in self.findings:
            lines.append(f"{f.level} {f.item.ljust(width)}  {f.detail}")
        lines.append("-" * 68)
        if self.failed:
            lines.append(f"发现 {self.failed} 项不一致")
        else:
            lines.append("未发现不一致")
        return "\n".join(lines)


def _load_db_orders(db: MySQL, goods_id: int) -> List[DbOrder]:
    rows = db.query(
        "SELECT o.order_id, o.user_id, u.nickname "
        "FROM miaosha_order o LEFT JOIN miaosha_user u ON o.user_id = u.id "
        "WHERE o.goods_id=%s",
        (goods_id,),
    )
    return [
        DbOrder(order_id=r["order_id"], user_id=str(r["user_id"]), nickname=str(r["nickname"] or ""))
        for r in rows
    ]


def _parse_uid(key: str, goods_id: int) -> str:
    """从 OrderKey:moug{uid}_{goodsId} 里取出 uid。"""
    body = key[len(ORDER_PREFIX):]
    suffix = f"_{goods_id}"
    return body[: -len(suffix)] if body.endswith(suffix) else body


def run(s: Settings, total_stock: int, detail: bool) -> int:
    goods_id = s.goods_id
    report = Report()

    with MySQL(s.db) as db, Cache(s.redis) as cache:
        db_stock = db.scalar(
            "SELECT stock_count FROM miaosha_goods WHERE goods_id=%s", (goods_id,), default=None
        )
        redis_stock = cache.get_int(RedisKeys.stock(goods_id))
        orders = _load_db_orders(db, goods_id)
        cache_order_keys = cache.keys(RedisKeys.order_pattern(goods_id))
        goods_over = cache.exists(RedisKeys.goods_over(goods_id))

        # 1. 库存一致
        if redis_stock is None:
            report.add(FAIL, "库存一致", f"Redis {RedisKeys.stock(goods_id)} 不存在，DB 库存 {db_stock}")
        elif db_stock == redis_stock:
            report.add(OK, "库存一致", f"DB {db_stock} == Redis {redis_stock}")
        else:
            report.add(
                FAIL,
                "库存一致",
                f"DB {db_stock} != Redis {redis_stock}，相差 {abs((db_stock or 0) - redis_stock)}",
            )

        # 2. 库存与订单数是否自洽（需要给出初始总库存）
        if total_stock and db_stock is not None:
            sold = total_stock - db_stock
            if sold == len(orders):
                report.add(OK, "库存与订单", f"总库存 {total_stock} - 剩余 {db_stock} = 已售 {sold} == 订单 {len(orders)}")
            else:
                report.add(
                    FAIL,
                    "库存与订单",
                    f"按库存推算已售 {sold}，实际订单 {len(orders)}，差 {abs(sold - len(orders))}（疑似超卖或漏单）",
                )

        # 3. 售罄标记
        if goods_over and redis_stock and redis_stock > 0:
            report.add(FAIL, "售罄标记", f"Redis 标记已售罄，但剩余库存 {redis_stock}")
        else:
            report.add(OK, "售罄标记", "已售罄" if goods_over else "未标记售罄")

        # 4. 幽灵订单：缓存说已下单，库里查不到
        db_uids: Dict[str, DbOrder] = {}
        for o in orders:
            db_uids[o.user_id] = o
            if o.nickname:
                db_uids[o.nickname] = o
        ghosts = [k for k in cache_order_keys if _parse_uid(k, goods_id) not in db_uids]
        if ghosts:
            report.add(
                FAIL, "幽灵订单", f"{len(ghosts)} 个缓存标记在库里无对应订单：{', '.join(ghosts[:5])}"
            )
        else:
            report.add(OK, "幽灵订单", f"{len(cache_order_keys)} 个缓存标记均可对上数据库订单")

        # 5. 漏缓存：库里有订单，缓存没有标记
        cache_uids = {_parse_uid(k, goods_id) for k in cache_order_keys}
        missing = [
            o for o in orders if o.user_id not in cache_uids and (not o.nickname or o.nickname not in cache_uids)
        ]
        if missing:
            report.add(
                WARN,
                "漏缓存",
                f"{len(missing)} 笔数据库订单没有缓存标记，重复下单判定会失效",
            )
        else:
            report.add(OK, "漏缓存", f"{len(orders)} 笔数据库订单均有缓存标记")

        if detail:
            report.add(
                OK,
                "明细",
                f"DB 订单 {[(o.user_id, o.order_id) for o in orders][:5]}；缓存 key {cache_order_keys[:5]}",
            )

    print(report.render(goods_id))
    return 1 if report.failed else 0
