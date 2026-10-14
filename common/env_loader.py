# -*- coding: utf-8 -*-
"""数据层：环境与测试账号。换环境只改这个文件。"""
import os
import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env() -> dict:
    with open(os.path.join(BASE, "data", "env.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)
