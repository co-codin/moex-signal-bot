from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ruff_precommit_and_docker_files_exist():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "[tool.ruff]" in pyproject
    assert "[tool.ruff.lint]" in pyproject
    assert '"redis>=5.0"' in pyproject
    assert '"fastapi>=0.115"' in pyproject
    assert '"uvicorn[standard]>=0.30"' in pyproject
    assert (ROOT / ".pre-commit-config.yaml").exists()
    assert (ROOT / "Dockerfile").exists()
    assert (ROOT / "docker-compose.yml").exists()
    assert (ROOT / ".dockerignore").exists()
    assert "redis:7-alpine" in compose
    assert "--scanner-scheduler" in compose
    assert "--scanner-worker" in compose
    assert "admin-web:" in compose
    assert "--admin-web" in compose
    assert '"8080:8080"' in compose
    assert "DATABASE_URL: ${DATABASE_URL:-postgresql://moex:change-me@postgres:5432/moex_signal_bot}" in compose
    assert "REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}" in compose
    assert "ACCESS_CONTROL_ENABLED: ${ACCESS_CONTROL_ENABLED:-false}" in compose
    assert "check:" in makefile
    assert "compose-up:" in makefile
    assert "workers:" in makefile
    assert "admin-web:" in makefile


def test_admin_web_environment_and_docs_are_present():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "ACCESS_CONTROL_ENABLED=false" in env_example
    assert "ADMIN_CHAT_IDS=" in env_example
    assert "ADMIN_WEB_USERNAME=" in env_example
    assert "ADMIN_WEB_PASSWORD=" in env_example
    assert "ADMIN_WEB_PORT=8080" in env_example
    assert "Админ-панель доступа" in readme
    assert "--admin-web" in readme


def test_project_agents_and_skill_are_present():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill = (ROOT / ".codex" / "skills" / "moex-signal-bot" / "SKILL.md").read_text(encoding="utf-8")

    assert "MOEX Signal Bot" in agents
    assert "Не коммитьте реальные токены" in agents
    assert "name: moex-signal-bot" in skill
    assert "ALGOPACK" in skill
