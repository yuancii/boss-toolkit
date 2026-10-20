"""Skill 脚本：从 stdin 读 {"sql": "..."}，只读执行并输出 JSON。

约定：stdout 永远是合法 JSON —— 任何失败都走 {"ok": false, "error": ...}，
连不上库、缺环境变量、SQL 出错都不抛 traceback。
"""
import json
import os
import re
import sys

DEFAULT_LIMIT = 200

# 末尾已有 LIMIT 时不重复追加：兼容 "LIMIT 10"、"LIMIT 10 OFFSET 20"、"LIMIT 20, 10"
_HAS_LIMIT_RE = re.compile(
    r"\blimit\s+\d+(\s*,\s*\d+)?(\s+offset\s+\d+)?\s*$", re.IGNORECASE
)


def fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))


def ensure_limit(sql: str, limit: int = DEFAULT_LIMIT) -> str:
    """SQL 末尾已有 LIMIT 就原样返回，否则补上 LIMIT。"""
    if _HAS_LIMIT_RE.search(sql):
        return sql
    return f"{sql}\nLIMIT {int(limit)}"


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        fail("入参不是合法 JSON")
        return

    sql = (payload.get("sql") or "").strip().rstrip(";")
    if not sql.lower().startswith(("select", "with")):
        fail("只允许 SELECT / WITH")
        return
    if ";" in sql:
        fail("不允许一次执行多条语句")
        return

    try:
        limit = int(payload.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    if limit <= 0:
        limit = DEFAULT_LIMIT
    statement = ensure_limit(sql, limit)

    try:
        import pymysql
    except ImportError:
        fail("缺少 pymysql，请先 pip install pymysql")
        return

    try:
        conn = pymysql.connect(
            host=os.environ["MYSQL_HOST"],
            port=int(os.environ.get("MYSQL_PORT", 3306)),
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            database=os.environ["MYSQL_DB"],
            charset="utf8mb4",
            connect_timeout=10,
        )
    except KeyError as exc:
        fail(f"缺少环境变量: {exc}")
        return
    except Exception as exc:  # pymysql 的异常类型较多，统一兜住
        fail(f"{type(exc).__name__}: {exc}")
        return

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(statement)
            rows = cur.fetchmany(limit)
    except Exception as exc:
        fail(f"{type(exc).__name__}: {exc}")
        return
    finally:
        conn.close()

    print(json.dumps({"ok": True, "rows": rows}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
