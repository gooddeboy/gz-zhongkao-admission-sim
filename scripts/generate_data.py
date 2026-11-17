"""生成虚构演示数据并写入数据库。

用法：
    python scripts/generate_data.py --preset small
    python scripts/generate_data.py --preset demo --seed 2026
    python scripts/generate_data.py --preset full --seed 2026
    python scripts/generate_data.py --preset custom --middle 100 --high 30 --candidates 3000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import (  # noqa: E402
    DEFAULT_DB_PATH,
    connect,
    dataset_counts,
    get_meta,
    init_db,
    replace_dataset,
    unlock_dataset,
)
from app.generator import PRESETS, generate_dataset, generate_preset, load_fixture  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="生成虚构演示数据")
    parser.add_argument("--preset", default="demo", choices=["small", "medium", "demo", "full", "custom"])
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--middle", type=int, default=100)
    parser.add_argument("--high", type=int, default=30)
    parser.add_argument("--candidates", type=int, default=3000)
    parser.add_argument("--g1", type=int, default=712)
    parser.add_argument("--delta", type=int, default=40)
    parser.add_argument("--city-line", type=int, default=492)
    parser.add_argument("--auto-g1", action="store_true", help="按全体考生前 10% 计算 G₁")
    parser.add_argument("--force", action="store_true", help="数据被锁定时先创建新数据版本")
    args = parser.parse_args()

    conn = connect(args.db)
    init_db(conn)
    meta = get_meta(conn)
    if meta["locked"]:
        if not args.force:
            raise SystemExit("当前数据已被运行锁定；请加 --force 或先在界面创建新数据版本。")
        unlock_dataset(conn)

    start = time.time()
    if args.preset == "small":
        ds = load_fixture("small_main")
        seed = None
    elif args.preset == "custom":
        ds = generate_dataset(
            seed=args.seed,
            middle_count=args.middle,
            high_count=args.high,
            candidate_count=args.candidates,
            g1=args.g1,
            delta=args.delta,
            city_line=args.city_line,
            auto_g1=args.auto_g1,
        )
        seed = args.seed
    else:
        ds = generate_preset(args.preset, seed=args.seed)
        seed = args.seed

    counts = replace_dataset(
        conn, ds, seed=seed, delete_runs=True,
        note=f"CLI 生成 {args.preset}，种子 {seed}",
    )
    elapsed = time.time() - start
    print(f"生成完成（{args.preset}，{elapsed:.2f}s）")
    print("数据量：", counts)
    print("推荐参数：G₁=%d，Δ=%d，L=%d" % (ds.params.g1, ds.params.delta, ds.params.city_line))
    print("当前数据版本：", get_meta(conn)["version"])
    conn.close()


if __name__ == "__main__":
    main()
