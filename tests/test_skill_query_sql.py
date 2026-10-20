"""skill 里 query_sql 脚本的纯逻辑测试：不连数据库。

覆盖两处曾出问题的地方：
  ensure_limit  已有 LIMIT（含 OFFSET / 逗号写法）时不再追加第二个 LIMIT；
  main          非法入参、非 SELECT、多语句都返回 {"ok": false} 而不是抛异常。
"""

import importlib.util
import io
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skill-build"
    / "data-analysis-skill"
    / "scripts"
    / "query_sql.py"
)


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("skill_query_sql", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEnsureLimit:
    def test_appends_limit_when_missing(self, mod):
        sql = mod.ensure_limit("SELECT * FROM orders")
        assert sql.endswith("LIMIT 200")

    def test_keeps_plain_limit(self, mod):
        sql = "SELECT * FROM orders LIMIT 10"
        assert mod.ensure_limit(sql) == sql

    def test_keeps_limit_with_offset(self, mod):
        sql = "SELECT * FROM orders LIMIT 10 OFFSET 20"
        assert mod.ensure_limit(sql) == sql

    def test_keeps_comma_form_limit(self, mod):
        sql = "SELECT * FROM orders LIMIT 20, 10"
        assert mod.ensure_limit(sql) == sql

    def test_custom_limit_value(self, mod):
        assert mod.ensure_limit("SELECT 1", 5).endswith("LIMIT 5")


class TestMainRejectsBadInput:
    def _run(self, mod, capsys, monkeypatch, stdin_text: str) -> dict:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
        mod.main()
        return json.loads(capsys.readouterr().out)

    def test_invalid_json(self, mod, capsys, monkeypatch):
        result = self._run(mod, capsys, monkeypatch, "not json")
        assert result["ok"] is False
        assert "JSON" in result["error"]

    def test_rejects_non_select(self, mod, capsys, monkeypatch):
        result = self._run(mod, capsys, monkeypatch, '{"sql": "DELETE FROM orders"}')
        assert result["ok"] is False
        assert "SELECT" in result["error"]

    def test_rejects_multi_statement(self, mod, capsys, monkeypatch):
        result = self._run(mod, capsys, monkeypatch, '{"sql": "SELECT 1; SELECT 2"}')
        assert result["ok"] is False
        assert "多条" in result["error"]
