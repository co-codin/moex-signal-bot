from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ruff_precommit_and_docker_files_exist():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "[tool.ruff]" in pyproject
    assert "[tool.ruff.lint]" in pyproject
    assert '"redis>=5.0"' in pyproject
    assert (ROOT / ".pre-commit-config.yaml").exists()
    assert (ROOT / "Dockerfile").exists()
    assert (ROOT / "docker-compose.yml").exists()
    assert (ROOT / ".dockerignore").exists()
    assert "redis:7-alpine" in compose
    assert "--scanner-scheduler" in compose
    assert "--scanner-worker" in compose
    assert "check:" in makefile
    assert "compose-up:" in makefile
    assert "workers:" in makefile


def test_project_agents_and_skill_are_present():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill = (ROOT / ".codex" / "skills" / "moex-signal-bot" / "SKILL.md").read_text(encoding="utf-8")

    assert "MOEX Signal Bot" in agents
    assert "Не коммитьте реальные токены" in agents
    assert "name: moex-signal-bot" in skill
    assert "ALGOPACK" in skill
