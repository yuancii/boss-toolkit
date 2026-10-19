"""tools.py 的单元测试：pytest tests/test_tools.py -q

覆盖三类函数的主要分支与错误分支：
  send_message  正常发送 / 空文本
  query_sql     正常查询 / 非 SELECT 拒绝 / 库不存在
  read_excel    文件不存在 / 正常读取前 N 行
"""

import sqlite3
from pathlib import Path

import pytest

from tools import query_sql, read_excel, send_message


@pytest.fixture()
def demo_db(tmp_path: Path) -> Path:
    """临时建一个订单库，避免依赖 data/demo.db。"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(
            """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                category TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                order_date TEXT NOT NULL
            );
            """
        )
        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            [
                (1, "手机", 1, 3999.0, "2026-09-03"),
                (2, "手机", 2, 3999.0, "2026-09-11"),
                (3, "耳机", 3, 299.0, "2026-09-12"),
                (4, "平板", 2, 2599.0, "2026-10-05"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


class TestSendMessage:
    def test_returns_ok(self, capsys):
        result = send_message("测试消息")
        assert result["ok"] is True
        assert result["length"] == 4
        assert "测试消息" in capsys.readouterr().out

    def test_empty_text_rejected(self):
        result = send_message("")
        assert result["ok"] is False
        assert "不能为空" in result["error"]


class TestQuerySql:
    def test_group_by_query(self, demo_db: Path):
        result = query_sql(
            "SELECT category, SUM(quantity * unit_price) AS sales "
            "FROM orders GROUP BY category ORDER BY sales DESC",
            db_path=str(demo_db),
        )
        assert result["ok"] is True
        assert result["columns"] == ["category", "sales"]
        assert result["rows"][0]["category"] == "手机"   # 7998 最大

    def test_date_filter(self, demo_db: Path):
        result = query_sql(
            "SELECT id FROM orders WHERE order_date >= '2026-10-01' ORDER BY id",
            db_path=str(demo_db),
        )
        assert result["ok"] is True
        assert result["count"] == 1

    @pytest.mark.parametrize(
        "sql",
        [
            "DELETE FROM orders",
            "DROP TABLE orders",
            "UPDATE orders SET quantity = 0",
        ],
    )
    def test_rejects_write_sql(self, demo_db: Path, sql: str):
        result = query_sql(sql, db_path=str(demo_db))
        assert result["ok"] is False
        assert "SELECT" in result["error"]

    def test_missing_database(self, tmp_path: Path):
        result = query_sql("SELECT 1", db_path=str(tmp_path / "nope.db"))
        assert result["ok"] is False
        assert "不存在" in result["error"]

    def test_invalid_syntax(self, demo_db: Path):
        result = query_sql("SELECT * FROM no_such_table", db_path=str(demo_db))
        assert result["ok"] is False


class TestReadExcel:
    def test_missing_file(self):
        result = read_excel("no_such_file.xlsx")
        assert result["ok"] is False
        assert "不存在" in result["error"]

    def test_read_head_rows(self, tmp_path: Path):
        pd = pytest.importorskip("pandas", reason="pandas 未安装")
        pytest.importorskip("openpyxl", reason="openpyxl 未安装")

        path = tmp_path / "data.xlsx"
        pd.DataFrame(
            {
                "category": ["手机", "耳机", "平板"],
                "price": [3999, 299, 2599],
            }
        ).to_excel(path, index=False)

        result = read_excel(str(path), head=2)
        assert result["ok"] is True
        assert result["rows"] == 3
        assert result["columns"] == ["category", "price"]
        assert len(result["preview"]) == 2
        assert result["preview"][0]["category"] == "手机"
