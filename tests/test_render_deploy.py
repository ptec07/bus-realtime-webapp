from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_render_blueprint_exists_with_python_web_service():
    render_config = ROOT / "render.yaml"
    assert render_config.exists()

    text = render_config.read_text()
    assert "services:" in text
    assert "type: web" in text
    assert "runtime: python" in text
    assert "name: bus-realtime-webapp" in text
    assert "plan: free" in text
    assert 'buildCommand: "pip install -r requirements.txt"' in text
    assert 'startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"' in text


def test_render_blueprint_declares_required_service_key_env_var():
    render_config = ROOT / "render.yaml"
    text = render_config.read_text()

    assert "envVars:" in text
    assert "key: PUBLIC_DATA_SERVICE_KEY" in text
    assert "sync: false" in text


def test_readme_documents_render_deploy_commands():
    readme = ROOT / "README.md"
    text = readme.read_text()

    assert "## Render 배포" in text
    assert "render.yaml" in text
    assert "PUBLIC_DATA_SERVICE_KEY" in text
    assert "uvicorn app.main:app --host 0.0.0.0 --port $PORT" in text
