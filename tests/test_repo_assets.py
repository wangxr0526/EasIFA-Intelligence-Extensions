from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BASE_URL = "https://cadd.drugflow.com/easifa"
EXPECTED_DIRECTORY = (
    "/home/xiaoruiwang/data/ubuntu_work_beta/single_step_work/"
    "EasIFA2.0_Prod/easifa-web-extensions"
)


def test_repo_tracked_client_configs_target_easifa_web_extensions():
    expected_files = [
        ROOT / ".codex/config.toml",
        ROOT / ".claude/settings.local.json",
        ROOT / ".vscode/mcp.json",
        ROOT / ".copilot/mcp-config.json",
    ]

    for path in expected_files:
        assert path.exists(), f"Missing config asset: {path.relative_to(ROOT)}"
        content = path.read_text(encoding="utf-8")
        assert EXPECTED_BASE_URL in content
        assert EXPECTED_DIRECTORY in content
        assert "easifa-mcp" in content


def test_skill_requires_table_first_output_and_links():
    skill_path = ROOT / "skills/easifa-mcp-usage/SKILL.md"
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert "markdown tables" in content
    assert "result links" in content
    assert "submission_endpoint" in content
    assert "result_endpoint" in content
    assert "poll_url" in content
    assert "result_url" in content
    assert "| Job ID | Status |" in content
