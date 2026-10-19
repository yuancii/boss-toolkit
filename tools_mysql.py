"""MySQL 版查询函数：把 tools.py 里的 SQLite 版本换成真实业务库。

设计原则（模型生成的 SQL 不可信）：
  1. 只放行 SELECT / WITH；
  2. 强制补 LIMIT，避免一次拉几十万行；
  3. 建议用**只读账号**连接（GRANT SELECT ON db.* TO 'reader'@'%'）；
  4. 连接超时 + 查询超时，避免卡住整个脚本。

环境变量：
  MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DB
"""

import os
import re

DEFAULT_LIMIT = 200
STATEMENT_TIMEOUT_MS = 10_000

_SELECT_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_HAS_LIMIT_RE = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)


def _conn_config() -> dict:
    missing = [
        k for k in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DB")
        if not os.environ.get(k)
    ]
    if missing:
        raise RuntimeError(f"缺少 MySQL 环境变量: {', '.join(missing)}")
    return {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.environ.get("MYSQL_PORT", 3306)),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DB"],
        "connect_timeout": 10,
        "read_timeout": 30,
        "charset": "utf8mb4",
    }


def validate_sql(sql: str, limit: int = DEFAULT_LIMIT) -> str:
    """校验并补全 SQL：非 SELECT 直接拒绝，缺 LIMIT 时自动补上。"""
    statement = (sql or "").strip().rstrip(";")
    if not statement:
        raise ValueError("SQL 不能为空")
    if not _SELECT_RE.match(statement):
        raise ValueError("只允许 SELECT / WITH 查询")
    if ";" in statement:
        raise ValueError("不允许一次执行多条语句")
    if not _HAS_LIMIT_RE.search(statement):
        statement = f"{statement}\nLIMIT {int(limit)}"
    return statement


def query_sql(sql: str, limit: int = DEFAULT_LIMIT) -> dict:
    """执行只读查询，返回列名与结果行。异常以 {"ok": False, "error": ...} 返回。"""
    try:
        statement = validate_sql(sql, limit)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        import pymysql
    except ImportError:
        return {"ok": False, "error": "缺少 pymysql，请 pip install -r requirements.txt"}

    try:
        conn = pymysql.connect(**_conn_config())
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={STATEMENT_TIMEOUT_MS}")
                cursor.execute(statement)
                rows = cursor.fetchmany(int(limit))
                columns = [d[0] for d in cursor.description or []]
        finally:
            conn.close()
    except Exception as exc:  # pymysql 的异常类型较多，统一兜住
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return {"ok": True, "columns": columns, "rows": rows, "count": len(rows)}


TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "query_sql",
            "description": "对业务 MySQL 执行只读 SELECT 查询，最多返回 200 行",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SELECT 语句，不要加分号"},
                    "limit": {"type": "integer", "description": "返回行数上限，默认 200"},
                },
                "required": ["sql"],
            },
        },
    },
]

TOOL_FUNCS = {"query_sql": query_sql}


if __name__ == "__main__":
    # 手工验证：python tools_mysql.py "SELECT 1 AS n"
    import sys

    sql_arg = sys.argv[1] if len(sys.argv) > 1 else "SELECT 1 AS n"
    print(query_sql(sql_arg))
