import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vercel_config_exists_and_routes_to_python_entrypoint():
    vercel_config = ROOT / "vercel.json"
    assert vercel_config.exists()

    config = json.loads(vercel_config.read_text())
    assert config["version"] == 2
    rewrites = config.get("rewrites", [])
    assert {item["destination"] for item in rewrites} == {"/api/index"}


def test_vercel_python_entrypoint_exists_and_exposes_app():
    entrypoint = ROOT / "api" / "index.py"
    assert entrypoint.exists()
    content = entrypoint.read_text()
    assert "app =" in content or "from app.main import app" in content


def test_pyproject_contains_minimal_project_table_for_vercel_python_build():
    pyproject = ROOT / "pyproject.toml"
    assert pyproject.exists()
    text = pyproject.read_text()
    assert "[project]" in text
    assert "requires-python" in text
