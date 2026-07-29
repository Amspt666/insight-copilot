"""从 data/raw/*.csv.gz 构建 DuckDB 数据库（表名做了友好化重命名）。

DuckDB 原生支持读取 gzip 压缩 CSV，无需手动解压。
运行：python3 scripts/build_db.py
"""
from pathlib import Path

import shutil
import tempfile

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "olist.duckdb"

FILES = {
    "orders": "olist_orders_dataset.csv.gz",
    "order_items": "olist_order_items_dataset.csv.gz",
    "payments": "olist_order_payments_dataset.csv.gz",
    "reviews": "olist_order_reviews_dataset.csv.gz",
    "customers": "olist_customers_dataset.csv.gz",
    "products": "olist_products_dataset.csv.gz",
    "sellers": "olist_sellers_dataset.csv.gz",
    "category_translation": "product_category_name_translation.csv.gz",
}


def main() -> None:
    if DB.exists():
        print(f"{DB} 已存在，跳过构建（删除后重跑可重建）")
        return
    missing = [f for f in FILES.values() if not (RAW / f).exists()]
    if missing:
        raise SystemExit(f"缺少数据文件：{missing}，请先确认 data/raw/ 完整。")
    # 先在系统临时目录构建再拷贝：某些网络挂载盘（FUSE/OSS）与 DuckDB
    # 的写入方式不兼容，直接写目标路径可能产出损坏文件
    tmp = Path(tempfile.mkdtemp()) / "olist.duckdb"
    con = duckdb.connect(str(tmp))
    for table, fname in FILES.items():
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto('{RAW / fname}', header=true)")
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<22} {n:>7} rows")
    con.close()
    shutil.copyfile(tmp, DB)
    print(f"数据库已构建：{DB}")


if __name__ == "__main__":
    main()
