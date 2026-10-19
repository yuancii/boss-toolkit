"""端到端演示：生成示例数据库 → 不依赖大模型的本地调用 → 有 Key 时走 Agent。

运行：
    python demo.py            # 只跑本地部分（建库 + 直接调工具函数）
    python demo.py --agent    # 额外跑一次 Function Calling（需要 DEEPSEEK_API_KEY）
"""

import os
import sqlite3
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "demo.db"

SAMPLES = [
    (1, "手机", 1, 3999.0, "2026-09-03"),
    (2, "手机", 2, 3999.0, "2026-09-11"),
    (3, "耳机", 3, 299.0, "2026-09-12"),
    (4, "耳机", 1, 299.0, "2026-10-02"),
    (5, "平板", 2, 2599.0, "2026-10-05"),
    (6, "平板", 4, 2599.0, "2026-10-09"),
]


def build_db() -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
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
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)", SAMPLES
        )
        conn.commit()
    finally:
        conn.close()
    return DB_PATH


def local_checks() -> None:
    from tools import query_sql, send_message

    print("-- 建库:", build_db())
    print("-- 按品类统计销售额（SQL JOIN/GROUP BY 等价写法）:")
    print(query_sql(
        "SELECT category, SUM(quantity * unit_price) AS sales "
        "FROM orders GROUP BY category ORDER BY sales DESC"
    ))
    print("-- 9 月之后的订单:")
    print(query_sql(
        "SELECT id, category, order_date FROM orders "
        "WHERE order_date >= '2026-10-01' ORDER BY order_date"
    ))
    send_message("示例消息：数据已生成完毕")


def agent_demo() -> None:
    from llm_client import call_with_tools
    from tools import TOOL_FUNCS, TOOL_SPECS

    print("-- 交给模型的提问：")
    question = "帮我统计各品类销售额，按从高到低排序，然后把前两名发一条消息播报出来。"
    print(question)
    print("-- Agent 结果：")
    print(call_with_tools(question, TOOL_SPECS, TOOL_FUNCS))


if __name__ == "__main__":
    local_checks()
    if "--agent" in sys.argv:
        if not os.environ.get("DEEPSEEK_API_KEY"):
            print("未设置 DEEPSEEK_API_KEY，跳过 Agent 演示")
        else:
            agent_demo()
