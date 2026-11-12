# -*- coding: utf-8 -*-
"""存储访问层：唯一与 MySQL / Redis 建立连接的地方。

工具里的其它模块只调用这里的方法，不直接 import pymysql / redis，
换驱动或加连接池时只改这一个文件。
"""
from typing import Any, Dict, List, Optional

import pymysql
import redis
from pymysql.cursors import DictCursor

from tools.settings import DbConfig, RedisConfig


class MySQL:
    """MySQL 薄封装：所有 SQL 走参数化，不做字符串拼接。"""

    def __init__(self, cfg: DbConfig):
        self.cfg = cfg
        self._conn = None

    def connect(self) -> "MySQL":
        self._conn = pymysql.connect(
            host=self.cfg.host,
            port=self.cfg.port,
            user=self.cfg.user,
            password=self.cfg.password,
            database=self.cfg.name,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,
            connect_timeout=5,
        )
        return self

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "MySQL":
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def scalar(self, sql: str, params: tuple = (), default=None):
        rows = self.query(sql, params)
        if not rows:
            return default
        return next(iter(rows[0].values()))

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self._conn.cursor() as cur:
            return cur.execute(sql, params)

    def table_exists(self, name: str) -> bool:
        return bool(
            self.query(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name=%s",
                (self.cfg.name, name),
            )
        )


class Cache:
    """Redis 薄封装。"""

    def __init__(self, cfg: RedisConfig):
        self.cfg = cfg
        self._client = None

    def connect(self) -> "Cache":
        self._client = redis.Redis(
            host=self.cfg.host,
            port=self.cfg.port,
            db=self.cfg.db,
            password=self.cfg.password,
            decode_responses=True,
            socket_connect_timeout=5,
            # 本机 Redis 版本较老，不支持 RESP3 的 HELLO 握手，强制走 RESP2
            protocol=2,
        )
        self._client.ping()
        return self

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "Cache":
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get(self, key: str) -> Optional[str]:
        return self._client.get(key)

    def get_int(self, key: str) -> Optional[int]:
        val = self._client.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def set(self, key: str, value) -> None:
        self._client.set(key, value)

    def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return self._client.delete(*keys)

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(key))

    def keys(self, pattern: str) -> List[str]:
        return sorted(self._client.keys(pattern))

    def info(self, section: str = "server") -> dict:
        return self._client.info(section)


class RedisKeys:
    """Redis key 规则，逐条对应被测系统里的 KeyPrefix 实现。

    对应关系（Java 包 com.geekq.miaosha.redis）：
        GoodsKey.getMiaoshaGoodsStock   -> GoodsKey:gs{goodsId}      库存（无过期）
        OrderKey.getMiaoshaOrderByUidGid-> OrderKey:moug{uid}_{gid}  下单标记
        MiaoshaKey.getMiaoshaPath       -> MiaoshaKey:mp{uid}_{gid}  秒杀地址，60s
        MiaoshaKey.getMiaoshaVerifyCode -> MiaoshaKey:vc{uid}_{gid}  验证码，300s
        MiaoshaKey.isGoodsOver          -> MiaoshaKey:go{goodsId}    售罄标记
    """

    STOCK = "GoodsKey:gs{goods_id}"
    GOODS_OVER = "MiaoshaKey:go{goods_id}"
    ORDER = "OrderKey:moug{uid}_{goods_id}"
    PATH = "MiaoshaKey:mp{uid}_{goods_id}"
    VERIFY_CODE = "MiaoshaKey:vc{uid}_{goods_id}"

    @classmethod
    def stock(cls, goods_id: int) -> str:
        return cls.STOCK.format(goods_id=goods_id)

    @classmethod
    def goods_over(cls, goods_id: int) -> str:
        return cls.GOODS_OVER.format(goods_id=goods_id)

    @classmethod
    def order(cls, uid, goods_id: int) -> str:
        return cls.ORDER.format(uid=uid, goods_id=goods_id)

    @classmethod
    def path(cls, uid, goods_id: int) -> str:
        return cls.PATH.format(uid=uid, goods_id=goods_id)

    @classmethod
    def verify_code(cls, uid, goods_id: int) -> str:
        return cls.VERIFY_CODE.format(uid=uid, goods_id=goods_id)

    @classmethod
    def order_pattern(cls, goods_id: int) -> str:
        return f"OrderKey:moug*_{goods_id}"
