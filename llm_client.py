"""调用大模型 API 的最小封装（DeepSeek，兼容 OpenAI 的 /chat/completions 格式）。

只依赖 requests：HTTP POST + Bearer 鉴权 + JSON，不引入官方 SDK，
方便看清"底层到底发了什么"。
"""

import json
import os
import time

import requests

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
TIMEOUT = 60
RETRIES = 3

SYSTEM_DEFAULT = "你是一个严谨的助手，回答要简洁、准确，不确定时直接说明。"


def _headers() -> dict:
    if not API_KEY:
        raise RuntimeError("缺少环境变量 DEEPSEEK_API_KEY")
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _post(payload: dict, stream: bool = False):
    """统一 POST，自带 429 指数退避与超时重试。"""
    last_error = None
    for attempt in range(RETRIES):
        try:
            resp = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=_headers(),
                json=payload,
                timeout=TIMEOUT,
                stream=stream,
            )
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"请求失败: {last_error}")


def chat(
    prompt: str,
    system: str = SYSTEM_DEFAULT,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """一次性返回完整回答。"""
    resp = _post(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    )
    return resp.json()["choices"][0]["message"]["content"]


def chat_stream(prompt: str, system: str = SYSTEM_DEFAULT) -> None:
    """流式输出（SSE），像打字机一样逐字打印。"""
    resp = _post(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
        },
        stream=True,
    )
    with resp:
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            delta = json.loads(data)["choices"][0]["delta"]
            print(delta.get("content", ""), end="", flush=True)
    print()


def call_with_tools(
    prompt: str,
    tools: list[dict],
    tool_funcs: dict,
    system: str = SYSTEM_DEFAULT,
    max_rounds: int = 5,
) -> str:
    """Function Calling：模型返回 tool_calls，本地执行函数后把结果回传。

    tools       —— OpenAI 格式的函数描述（见 tools.py 里的 TOOL_SPECS）
    tool_funcs  —— {"函数名": 可调用对象}
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    for _ in range(max_rounds):
        resp = _post({"model": MODEL, "messages": messages, "tools": tools})
        message = resp.json()["choices"][0]["message"]
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return message.get("content") or ""

        messages.append(
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            name = call["function"]["name"]
            args = json.loads(call["function"].get("arguments") or "{}")
            func = tool_funcs.get(name)
            result = func(**args) if func else {"error": f"未知函数 {name}"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    return "已达到最大工具调用轮数，任务未完成"


if __name__ == "__main__":
    # 没有 API Key 时只展示用法，不发请求
    if not API_KEY:
        print("未设置 DEEPSEEK_API_KEY，示例跳过。可先 export 后再运行。")
    else:
        print(chat("用一句话解释什么是 REST API"))
        chat_stream("用三句话说明 SQL 里 JOIN 的作用")
