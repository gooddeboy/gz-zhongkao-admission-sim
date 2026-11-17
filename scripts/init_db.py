"""初始化数据库，可选加载小数据集。

用法：
    python scripts/init_db.py
    python scripts/init_db.py --fixture small_main
    python scripts/init_db.py --db data/demo.db --fixture small_main --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import DEFAULT_DB_PATH, connect, dataset_counts, get_meta, init_db, replace_dataset, unlock_dataset  # noqa: E402
from app.generator import load_fixture  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化录取模拟系统数据库")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="数据库路径")
    parser.add_argument("--fixture", default="", help="可选：加载 data/fixtures/<name>.json")
    parser.add_argument("--force", action="store_true", help="数据被锁定时先创建新数据版本")
    args = parser.parse_args()

    conn = connect(args.db)
    init_db(conn)
    meta = get_meta(conn)
    if args.force and meta["locked"]:
        unlock_dataset(conn)
        meta = get_meta(conn)
    if args.fixture:
        if meta["locked"]:
            raise SystemExit("当前数据库已被运行锁定；请加 --force 或先创建新数据版本。")
        ds = load_fixture(args.fixture)
        counts = replace_dataset(conn, ds, note=f"CLI 加载 {args.fixture}")
        print("已加载小数据集：", counts)
    else:
        print("数据库已初始化：", args.db)
    print("当前数据版本：", get_meta(conn)["version"])
    print("当前数据量：", dataset_counts(conn))
    conn.close()


if __name__ == "__main__":
    main()
