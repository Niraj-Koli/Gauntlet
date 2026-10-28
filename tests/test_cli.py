"""The `gauntlet` command, run in-process against a test database."""

import json

import pytest

from gauntlet import cli
from gauntlet import settings as settings_module
from gauntlet.container import build_container


@pytest.fixture
def run(settings, market, monkeypatch, capsys):
    """Run `gauntlet ARGS...` and return what it printed."""
    monkeypatch.setattr(cli, "build_container", lambda: build_container(settings, market))
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)

    def run(*args: str) -> str:
        capsys.readouterr()
        cli.main(list(args))
        return capsys.readouterr().out

    return run


def test_migrate_then_status(run):
    assert "up to date" in run("migrate")
    out = run("status")
    assert "Floor: active, no scheduler running" in out
    assert "Prices: fake" in out
    for name in ("Warren", "George", "Ray", "Cathie"):
        assert name in out
    assert "no runs yet" in out


def test_models_lists_the_catalog_and_missing_keys(run):
    out = run("models")
    assert "anthropic/claude-opus-5-5" in out
    assert "needs ANTHROPIC_API_KEY" in out
    assert "Any other LiteLLM id" in out


def test_set_model_and_guardrails(run):
    assert "Warren now trades with" in run("set-model", "warren", "anthropic/claude-opus-5-5")
    out = run("guardrails", "warren", json.dumps({"max_positions": 3}))
    assert json.loads(out)["max_positions"] == 3
    assert json.loads(run("guardrails", "warren"))["max_positions"] == 3
    with pytest.raises(SystemExit, match="JSON object"):
        run("guardrails", "warren", "[1]")


def test_run_now_pause_resume_and_reset(run):
    out = run("run-now", "all")
    assert out.count("Queued a run for") == 4
    assert "No scheduler is running" in out
    assert "Floor paused" in run("pause")
    assert "paused" in run("status").splitlines()[0]
    assert "Floor resumed" in run("resume")
    assert "Ray paused" in run("pause", "ray")
    assert "Ray resumed" in run("resume", "ray")
    assert run("reset", "warren").strip() == "Reset Warren"
    with pytest.raises(SystemExit, match="Unknown trader"):
        run("reset", "nobody")


def test_import_legacy_needs_a_file(run, tmp_path):
    with pytest.raises(SystemExit, match="No such file"):
        run("import-legacy", str(tmp_path / "missing.db"))


def test_openapi_writes_the_schema(run, tmp_path):
    out = tmp_path / "openapi.json"
    assert "Wrote" in run("openapi", "--out", str(out))
    schema = json.loads(out.read_text(encoding="utf-8"))
    assert "/api/v1/traders" in schema["paths"]
    assert json.loads(run("openapi"))["info"]["title"] == "Gauntlet"
