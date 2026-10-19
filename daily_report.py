"""每日报表脚本：查 MySQL 汇总昨天下单情况并输出，可挂计划任务 / cron。

用法：
    python daily_report.py                    # 统计昨天
    python daily_report.py --date 2026-10-18  # 指定日期
    python daily_report.py --dry-run          # 只打印 SQL，不连库

环境变量（见 .env.example）：
    MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DB

挂定时任务：
    Windows: schtasks /create /tn "daily-report" /tr "python E:\\Code file\\boss\\daily_report.py" /sc daily /st 09:00
    Linux:   0 9 * * * cd /path/boss && /usr/bin/python3 daily_report.py >> /var/log/daily_report.log 2>&1
"""

import argparse
import datetime as dt
import sys

from tools_mysql import query_sql, validate_sql

SUMMARY_SQL = """
SELECT category AS 品类,
       COUNT(*) AS 订单数,
       SUM(quantity) AS 件数,
       SUM(quantity * unit_price) AS 销售额
FROM orders
WHERE order_date >= '{day}' AND order_date < '{next_day}'
GROUP BY category
ORDER BY 销售额 DESC
"""


def build_sql(day: dt.date) -> str:
    next_day = day + dt.timedelta(days=1)
    return SUMMARY_SQL.format(day=day.isoformat(), next_day=next_day.isoformat()).strip()


def format_report(day: dt.date, result: dict) -> str:
    if not result.get("ok"):
        return f"[{day}] 查询失败：{result.get('error')}"

    rows = result.get("rows") or []
    if not rows:
        return f"[{day}] 无订单数据"

    total = sum(float(r.get("销售额") or 0) for r in rows)
    lines = [f"[{day}] 日报：共 {len(rows)} 个品类，合计销售额 {total:,.2f}"]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"  {index}. {row.get('品类')}："
            f"{row.get('订单数')} 单 / {row.get('件数')} 件 / "
            f"{float(row.get('销售额') or 0):,.2f}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="MySQL 每日订单汇总报表")
    parser.add_argument("--date", help="统计日期 YYYY-MM-DD，默认昨天")
    parser.add_argument("--dry-run", action="store_true", help="只打印 SQL，不连库")
    args = parser.parse_args()

    if args.date:
        try:
            day = dt.date.fromisoformat(args.date)
        except ValueError:
            print(f"--date 格式错误: {args.date}（应为 YYYY-MM-DD）", file=sys.stderr)
            return 2
    else:
        day = dt.date.today() - dt.timedelta(days=1)

    sql = build_sql(day)
    if args.dry_run:
        print("-- 将要执行的 SQL：")
        print(validate_sql(sql))
        return 0

    print(format_report(day, query_sql(sql)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
