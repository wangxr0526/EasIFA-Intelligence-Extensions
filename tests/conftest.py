import pytest


@pytest.fixture(autouse=True)
def isolated_owner_state(tmp_path, monkeypatch):
    """Tests must neither reuse real credentials nor create files in a user's home."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("EASIFA_SESSION_KEY", raising=False)
    monkeypatch.delenv("EASIFA_MCP_SESSION_FILE", raising=False)
