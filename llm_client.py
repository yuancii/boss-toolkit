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
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

SYSTEM_DEFAULT = "你是一个严谨的助手，回答要简洁、准确，不确定时直接说明。"


def _headers() -> dict:
    if not API_KEY:
        raise RuntimeError("缺少环境变量 DEEPSEEK_API_KEY")
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _post(payload: dict, stream: bool = False):
    """统一 POST：网络错误与 429/5xx 指数退避重试，其余 4xx 立刻失败。

    只有"再试一次可能成功"的失败才值得重试；400/401/403 是参数或鉴权问题，
    重试只会白等几秒，还把真正的状态码与响应体埋掉。
    """
    last_error = ""
    for attempt in range(RETRIES):
        try:
            resp = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=_headers(),
                json=payload,
                timeout=TIMEOUT,
                stream=stream,
            )
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if resp.ok:
                return resp
            last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if resp.status_code not in RETRYABLE_STATUS:
                raise RuntimeError(f"请求失败 {last_error}")
        if attempt < RETRIES - 1:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"请求失败 {last_error}")


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


def _run_tool(tool_funcs: dict, function: dict) -> dict:
    """执行一次工具调用：函数不存在、参数不是 JSON、函数内部抛错都折成 {"error"}。

    工具失败不该中断整个 Agent 循环——把错误回灌给模型，它才有机会改参数重试。
    """
    name = function.get("name") or ""
    func = tool_funcs.get(name)
    if func is None:
        return {"error": f"未知函数 {name}"}
    try:
        args = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        return {"error": f"参数不是合法 JSON: {exc}"}
    if not isinstance(args, dict):
        return {"error": "参数必须是 JSON 对象"}
    try:
        return func(**args)
    except TypeError as exc:
        return {"error": f"参数不匹配: {exc}"}
    except Exception as exc:  # 工具自身的失败同样回灌给模型
        return {"error": f"{type(exc).__name__}: {exc}"}


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
            result = _run_tool(tool_funcs, call["function"])
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
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
