"""把常用功能封装成 Python 函数，供 AI Agent（Function Calling）调用。

三个函数对应岗位描述里的典型任务：
  send_message  发消息
  read_excel    读 Excel
  query_sql     查数据库（SQLite，readonly）

每个函数都返回可直接序列化成 JSON 的 dict，方便塞回模型上下文。
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "demo.db"
DEFAULT_PREVIEW = 5


def send_message(text: str, channel: str = "console") -> dict:
    """发送一条消息（这里打印到控制台，实际可换成钉钉/企业微信/邮件）。"""
    if not text:
        return {"ok": False, "error": "text 不能为空"}
    print(f"[{channel}] {text}")
    return {"ok": True, "channel": channel, "length": len(text)}


def read_excel(path: str, sheet: str | None = None, head: int = DEFAULT_PREVIEW) -> dict:
    """读取 Excel 前几行，返回列名、行数与预览数据。"""
    try:
        import pandas as pd
    except ImportError:
        return {"ok": False, "error": "缺少 pandas，请先 pip install -r requirements.txt"}

    file = Path(path)
    if not file.exists():
        return {"ok": False, "error": f"文件不存在: {path}"}

    df = pd.read_excel(file, sheet_name=sheet or 0)
    return {
        "ok": True,
        "columns": [str(c) for c in df.columns],
        "rows": int(len(df)),
        "preview": df.head(max(1, int(head))).to_dict(orient="records"),
    }


def query_sql(sql: str, db_path: str | None = None) -> dict:
    """执行只读 SQL（SELECT），返回列名与结果行。"""
    statement = (sql or "").strip()
    if not statement.lower().startswith(("select", "with")):
        return {"ok": False, "error": "只允许 SELECT / WITH 查询"}

    db = Path(db_path) if db_path else DB_PATH
    if not db.exists():
        return {"ok": False, "error": f"数据库不存在: {db}，先运行 python demo.py 生成示例库"}

    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(statement).fetchmany(50)
            columns = [d[0] for d in conn.execute(statement).description or []]
        finally:
            conn.close()
        return {
            "ok": True,
            "columns": columns,
            "rows": [dict(r) for r in rows],
            "count": len(rows),
        }
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc)}


def _spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# 交给模型的函数描述（OpenAI tools 格式）
TOOL_SPECS = [
    _spec(
        "send_message",
        "给指定渠道发送一条文本消息",
        {
            "text": {"type": "string", "description": "消息内容"},
            "channel": {"type": "string", "description": "渠道，默认 console"},
        },
        ["text"],
    ),
    _spec(
        "read_excel",
        "读取 Excel 文件并返回列名、行数与前几行预览",
        {
            "path": {"type": "string", "description": "Excel 文件路径"},
            "sheet": {"type": "string", "description": "工作表名，默认第一个"},
            "head": {"type": "integer", "description": "预览行数，默认 5"},
        },
        ["path"],
    ),
    _spec(
        "query_sql",
        "对本地 SQLite 数据库执行只读 SELECT 查询",
        {
            "sql": {"type": "string", "description": "SELECT 语句"},
            "db_path": {"type": "string", "description": "可选，数据库路径"},
        },
        ["sql"],
    ),
]

TOOL_FUNCS = {
    "send_message": send_message,
    "read_excel": read_excel,
    "query_sql": query_sql,
}
