"""llm_client 的 HTTP 层与工具执行测试：mock 掉 requests，不发真实请求。

覆盖两个曾经的问题：
  _post      4xx 也会被重试，最终错误信息丢掉状态码与响应体；
  _run_tool  工具抛异常会中断整个 Agent 循环，而不是把错误回灌给模型。
"""

import json

import pytest
import requests

import llm_client


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload, ensure_ascii=False)

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """不真的 sleep，并给一个假 API Key。"""
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_: None)
    monkeypatch.setattr(llm_client, "API_KEY", "sk-test")


def patch_post(monkeypatch, responses):
    """按顺序返回给定响应（或抛给定异常），返回记录到的调用列表。"""
    calls = []

    def _post(*args, **kwargs):
        calls.append((args, kwargs))
        item = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(llm_client.requests, "post", _post)
    return calls


class TestPost:
    def test_client_error_is_not_retried(self, monkeypatch):
        calls = patch_post(monkeypatch, [FakeResponse(401, text='{"error":"bad key"}')])
        with pytest.raises(RuntimeError, match="401"):
            llm_client._post({"model": "x"})
        assert len(calls) == 1

    def test_error_message_keeps_response_body(self, monkeypatch):
        patch_post(monkeypatch, [FakeResponse(403, text="forbidden-detail")])
        with pytest.raises(RuntimeError, match="forbidden-detail"):
            llm_client._post({"model": "x"})

    def test_rate_limit_is_retried_then_succeeds(self, monkeypatch):
        calls = patch_post(
            monkeypatch, [FakeResponse(429, text="slow down"), FakeResponse(200, {"ok": 1})]
        )
        resp = llm_client._post({"model": "x"})
        assert resp.status_code == 200
        assert len(calls) == 2

    def test_server_error_exhausts_retries(self, monkeypatch):
        calls = patch_post(monkeypatch, [FakeResponse(500, text="boom")])
        with pytest.raises(RuntimeError, match="500"):
            llm_client._post({"model": "x"})
        assert len(calls) == llm_client.RETRIES

    def test_network_error_is_retried(self, monkeypatch):
        calls = patch_post(
            monkeypatch, [requests.ConnectionError("down"), FakeResponse(200, {"ok": 1})]
        )
        resp = llm_client._post({"model": "x"})
        assert resp.status_code == 200
        assert len(calls) == 2

    def test_missing_api_key_raises_before_request(self, monkeypatch):
        calls = patch_post(monkeypatch, [FakeResponse(200)])
        monkeypatch.setattr(llm_client, "API_KEY", "")
        with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
            llm_client._post({"model": "x"})
        assert calls == []


def tool_call(call_id: str, name: str, arguments: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            }
        ]
    }


def final_answer(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def patch_llm(monkeypatch, payloads):
    """按顺序返回模型响应，并记录每次请求体。"""
    queue = list(payloads)
    sent = []

    def _post(payload, stream=False):
        sent.append(payload)
        return FakeResponse(200, queue[min(len(sent) - 1, len(queue) - 1)])

    monkeypatch.setattr(llm_client, "_post", _post)
    return sent


def tool_errors(sent) -> list[dict]:
    """从最后一次请求的 messages 里取出 role=tool 的结果。"""
    return [
        json.loads(m["content"])
        for m in sent[-1]["messages"]
        if m.get("role") == "tool"
    ]


class TestRunTool:
    def test_unknown_function(self):
        result = llm_client._run_tool({}, {"name": "nope", "arguments": "{}"})
        assert "未知函数" in result["error"]

    def test_bad_json_arguments(self):
        result = llm_client._run_tool({"f": lambda: 1}, {"name": "f", "arguments": "{oops"})
        assert "JSON" in result["error"]

    def test_non_object_arguments(self):
        result = llm_client._run_tool({"f": lambda: 1}, {"name": "f", "arguments": "[1, 2]"})
        assert "JSON 对象" in result["error"]

    def test_wrong_kwargs(self):
        result = llm_client._run_tool({"f": lambda a: a}, {"name": "f", "arguments": '{"b": 1}'})
        assert "参数不匹配" in result["error"]

    def test_ok(self):
        result = llm_client._run_tool({"f": lambda a: {"ok": a}}, {"name": "f", "arguments": '{"a": 2}'})
        assert result == {"ok": 2}


class TestCallWithTools:
    def test_tool_exception_is_fed_back(self, monkeypatch):
        def boom():
            raise ValueError("数据库崩了")

        sent = patch_llm(
            monkeypatch,
            [tool_call("c1", "query_sql", "{}"), final_answer("已完成")],
        )
        answer = llm_client.call_with_tools("查一下", [], {"query_sql": boom})
        assert answer == "已完成"
        assert "数据库崩了" in tool_errors(sent)[0]["error"]

    def test_unknown_tool_is_fed_back(self, monkeypatch):
        sent = patch_llm(monkeypatch, [tool_call("c1", "nope", "{}"), final_answer("好")])
        assert llm_client.call_with_tools("x", [], {}) == "好"
        assert "未知函数" in tool_errors(sent)[0]["error"]

    def test_bad_arguments_are_fed_back(self, monkeypatch):
        sent = patch_llm(monkeypatch, [tool_call("c1", "f", "{oops"), final_answer("好")])
        assert llm_client.call_with_tools("x", [], {"f": lambda: 1}) == "好"
        assert "JSON" in tool_errors(sent)[0]["error"]

    def test_stops_after_max_rounds(self, monkeypatch):
        sent = patch_llm(monkeypatch, [tool_call("c1", "f", "{}")])
        answer = llm_client.call_with_tools("x", [], {"f": lambda: {"ok": 1}}, max_rounds=3)
        assert "最大工具调用轮数" in answer
        assert len(sent) == 3
