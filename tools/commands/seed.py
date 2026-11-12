# -*- coding: utf-8 -*-
"""seed：把数据重置到可重复执行的基线。

取代原来散落在 README 与 reset-data.bat 里的手工 SQL + redis-cli：
    1. MySQL 商品库存回到指定值
    2. 清空该商品的秒杀订单与订单详情
    3. Redis 同步库存、清下单标记 / 秒杀地址 / 验证码 / 售罄标记

为什么要同时清三层：秒杀系统的"是否已下单"判定读的是 Redis 里的
OrderKey 缓存，只删数据库订单、不清缓存，同一个账号仍然下不了单。
"""
from dataclasses import dataclass, field
from typing import List

from tools.settings import Settings
from tools.storage import Cache, MySQL, RedisKeys


@dataclass
class Snapshot:
    db_stock: int = 0
    order_count: int = 0
    cache_stock: object = None
    order_keys: List[str] = field(default_factory=list)


def _snapshot(db: MySQL, cache: Cache, goods_id: int) -> Snapshot:
    return Snapshot(
        db_stock=db.scalar(
            "SELECT stock_count FROM miaosha_goods WHERE goods_id=%s", (goods_id,), default=-1
        ),
        order_count=db.scalar(
            "SELECT COUNT(*) FROM miaosha_order WHERE goods_id=%s", (goods_id,), default=0
        ),
        cache_stock=cache.get_int(RedisKeys.stock(goods_id)),
        order_keys=cache.keys(RedisKeys.order_pattern(goods_id)),
    )


def _print_snapshot(title: str, snap: Snapshot) -> None:
    print(f"  {title}")
    print(f"    MySQL 库存      : {snap.db_stock}")
    print(f"    MySQL 订单数    : {snap.order_count}")
    print(f"    Redis 库存      : {snap.cache_stock if snap.cache_stock is not None else '(不存在)'}")
    print(f"    Redis 下单标记  : {len(snap.order_keys)} 个 {snap.order_keys if snap.order_keys else ''}".rstrip())


def run(s: Settings, stock: int, uid: str, dry_run: bool) -> int:
    goods_id = s.goods_id
    uid = uid or s.user_mobile

    with MySQL(s.db) as db, Cache(s.redis) as cache:
        before = _snapshot(db, cache, goods_id)

        sql_update = "UPDATE miaosha_goods SET stock_count=%s WHERE goods_id=%s"
        sql_del_order = "DELETE FROM miaosha_order WHERE goods_id=%s"
        sql_del_info = "DELETE FROM order_info WHERE goods_id=%s"

        print(f"\n重置基线  goods_id={goods_id}  目标库存={stock}  uid={uid or '(未指定)'}")
        print("-" * 68)
        _print_snapshot("重置前", before)

        if dry_run:
            print("\n  [dry-run] 将执行：")
            print(f"    {sql_update}  -> ({stock}, {goods_id})")
            print(f"    {sql_del_order}  -> ({goods_id})")
            print(f"    {sql_del_info}  -> ({goods_id})")
            print(f"    SET  {RedisKeys.stock(goods_id)} = {stock}")
            print(f"    DEL  {RedisKeys.order_pattern(goods_id)}  (扫描全部匹配 key)")
            for key in (RedisKeys.goods_over(goods_id),):
                print(f"    DEL  {key}")
            if uid:
                print(f"    DEL  {RedisKeys.path(uid, goods_id)}")
                print(f"    DEL  {RedisKeys.verify_code(uid, goods_id)}")
            print("-" * 68)
            print("未做任何修改")
            return 0

        db.execute(sql_update, (stock, goods_id))
        db.execute(sql_del_order, (goods_id,))
        db.execute(sql_del_info, (goods_id,))

        cache.set(RedisKeys.stock(goods_id), stock)
        deleted_cache = cache.delete(*before.order_keys) if before.order_keys else 0
        extra_keys = [RedisKeys.goods_over(goods_id)]
        if uid:
            extra_keys += [RedisKeys.path(uid, goods_id), RedisKeys.verify_code(uid, goods_id)]
        cache.delete(*extra_keys)

        after = _snapshot(db, cache, goods_id)
        print(f"\n  已执行：更新库存 1 行，删除订单 {before.order_count} 条，"
              f"清理 Redis 缓存 {deleted_cache + len(extra_keys)} 个 key")
        _print_snapshot("重置后", after)
        print("-" * 68)
        print("基线已就绪，可以执行 pytest -m miaosha_write")
        return 0
