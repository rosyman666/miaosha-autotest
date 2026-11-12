# -*- coding: utf-8 -*-
"""命令行入口。

用法：
    python -m tools doctor
    python -m tools seed --stock 10
    python -m tools seed --stock 10 --dry-run
    python -m tools reconcile --total 10
"""
import argparse
import sys

from tools.commands import doctor, reconcile, seed
from tools.settings import load_settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools",
        description="秒杀系统接口测试工程的配套工具：环境自检 / 数据重置 / 缓存对账",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="检查 MySQL、Redis、应用、RabbitMQ 是否就绪")

    p_seed = sub.add_parser("seed", help="重置秒杀数据基线（库存 / 订单 / 缓存）")
    p_seed.add_argument("--stock", type=int, default=10, help="目标库存，默认 10")
    p_seed.add_argument("--uid", default="", help="清理该用户的秒杀地址与验证码缓存，默认取 env.yaml 的账号")
    p_seed.add_argument("--dry-run", action="store_true", help="只打印将要执行的操作，不修改数据")

    p_rec = sub.add_parser("reconcile", help="对账 MySQL 与 Redis 的库存和订单状态")
    p_rec.add_argument("--total", type=int, default=0, help="初始总库存；给出后会校验「已售数量 == 订单数」")
    p_rec.add_argument("--detail", action="store_true", help="打印订单与缓存 key 明细")

    return parser


def main(argv=None) -> int:
    # Windows 控制台默认 GBK，中文与特殊符号会抛 UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = _build_parser().parse_args(argv)
    settings = load_settings()

    if args.command == "doctor":
        return doctor.run(settings)
    if args.command == "seed":
        return seed.run(settings, stock=args.stock, uid=args.uid, dry_run=args.dry_run)
    if args.command == "reconcile":
        return reconcile.run(settings, total_stock=args.total, detail=args.detail)
    return 2


if __name__ == "__main__":
    sys.exit(main())
