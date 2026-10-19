"""tools_mysql 的纯逻辑测试：不连数据库，只测 SQL 校验与报表格式化。"""

import datetime as dt

import pytest

from daily_report import build_sql, format_report
from tools_mysql import validate_sql


class TestValidateSql:
    def test_rejects_non_select(self):
        with pytest.raises(ValueError, match="只允许 SELECT"):
            validate_sql("DELETE FROM orders")

    def test_rejects_multi_statement(self):
        with pytest.raises(ValueError, match="多条"):
            validate_sql("SELECT 1; SELECT 2")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="不能为空"):
            validate_sql("   ")

    def test_appends_limit_when_missing(self):
        sql = validate_sql("SELECT * FROM orders")
        assert sql.endswith("LIMIT 200")

    def test_keeps_existing_limit(self):
        sql = validate_sql("SELECT * FROM orders LIMIT 10")
        assert sql.count("LIMIT") == 1
        assert "LIMIT 200" not in sql

    def test_accepts_with_cte(self):
        assert validate_sql("WITH t AS (SELECT 1) SELECT * FROM t").startswith("WITH")


class TestDailyReport:
    def test_build_sql_covers_one_day(self):
        sql = build_sql(dt.date(2026, 10, 18))
        assert "'2026-10-18'" in sql
        assert "'2026-10-19'" in sql
        assert "GROUP BY category" in sql

    def test_format_report_with_rows(self):
        day = dt.date(2026, 10, 18)
        result = {
            "ok": True,
            "rows": [
                {"品类": "平板", "订单数": 2, "件数": 4, "销售额": "15594.00"},
                {"品类": "手机", "订单数": 2, "件数": 3, "销售额": "11997.00"},
            ],
        }
        text = format_report(day, result)
        assert "2026-10-18" in text
        assert "平板" in text and "手机" in text
        assert "27,591.00" in text   # 合计

    def test_format_report_without_rows(self):
        text = format_report(dt.date(2026, 10, 18), {"ok": True, "rows": []})
        assert "无订单数据" in text

    def test_format_report_with_error(self):
        text = format_report(dt.date(2026, 10, 18), {"ok": False, "error": "连接超时"})
        assert "查询失败" in text and "连接超时" in text
