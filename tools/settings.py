# -*- coding: utf-8 -*-
"""配置分层：环境变量 > data/env.local.yaml > data/env.yaml。

为什么要分三层：
    env.yaml        入库，只放非敏感的默认值（地址、端口、库名），密码留空
    env.local.yaml  不入库（见 .gitignore），放本机的账号密码
    环境变量        最高优先级，CI 或临时切换环境时不用改文件
"""
import os
from dataclasses import dataclass
from typing import Optional

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


@dataclass
class DbConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = ""
    name: str = "miaosha"

    @property
    def dsn(self) -> str:
        return f"mysql://{self.user}@{self.host}:{self.port}/{self.name}"


@dataclass
class RedisConfig:
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None

    @property
    def dsn(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class Settings:
    base_url: str = "http://localhost:8003"
    goods_id: int = 1
    user_mobile: str = ""
    user_password_cipher: str = ""
    db: DbConfig = None
    redis: RedisConfig = None


def _read_yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _env(name: str, default=None):
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def load_settings() -> Settings:
    """按优先级合并三层配置后返回不可变的配置对象。"""
    merged = {}
    for path in (
        os.path.join(DATA_DIR, "env.yaml"),
        os.path.join(DATA_DIR, "env.local.yaml"),  # 本地覆盖，不入库
    ):
        for key, value in _read_yaml(path).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value

    db_raw = merged.get("database") or {}
    redis_raw = merged.get("redis") or {}
    user_raw = merged.get("user") or {}

    db = DbConfig(
        host=_env("MIAOSHA_DB_HOST", db_raw.get("host", "127.0.0.1")),
        port=int(_env("MIAOSHA_DB_PORT", db_raw.get("port", 3306))),
        user=_env("MIAOSHA_DB_USER", db_raw.get("user", "root")),
        password=_env("MIAOSHA_DB_PASSWORD", db_raw.get("password", "")),
        name=_env("MIAOSHA_DB_NAME", db_raw.get("name", "miaosha")),
    )
    redis = RedisConfig(
        host=_env("MIAOSHA_REDIS_HOST", redis_raw.get("host", "127.0.0.1")),
        port=int(_env("MIAOSHA_REDIS_PORT", redis_raw.get("port", 6379))),
        db=int(_env("MIAOSHA_REDIS_DB", redis_raw.get("db", 0))),
        password=_env("MIAOSHA_REDIS_PASSWORD", redis_raw.get("password")) or None,
    )

    return Settings(
        base_url=_env("MIAOSHA_BASE_URL", merged.get("base_url", "http://localhost:8003")),
        goods_id=int(_env("MIAOSHA_GOODS_ID", merged.get("goods_id", 1))),
        user_mobile=user_raw.get("mobile", ""),
        user_password_cipher=user_raw.get("password_cipher", ""),
        db=db,
        redis=redis,
    )
