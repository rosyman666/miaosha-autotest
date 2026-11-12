# -*- coding: utf-8 -*-
"""环境配置读取。换环境只改 data/env.yaml，或用环境变量覆盖。"""
import os

import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env() -> dict:
    with open(os.path.join(BASE, "data", "env.yaml"), encoding="utf-8") as f:
        env = yaml.safe_load(f)

    # 与 tools/settings.py 保持同一套环境变量名，CI 或临时换环境时不用改文件
    env["base_url"] = os.environ.get("MIAOSHA_BASE_URL", env["base_url"])
    env["goods_id"] = int(os.environ.get("MIAOSHA_GOODS_ID", env["goods_id"]))
    return env
