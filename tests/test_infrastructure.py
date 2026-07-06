"""Smoke-tests for the infrastructure pre-flight module."""

from __future__ import annotations

import pytest

from src.mcp_bridge import validate_action_dependencies


class TestValidateActionDependencies:
    """Unit tests for the conditional fail-fast validator."""

    def test_all_required_present_and_healthy(self):
        """Should pass silently when every required server is up."""
        status = {
            "codegraph_mcp": (True, ["tool_a"]),
            "jira_mcp": (True, ["tool_b"]),
        }
        validate_action_dependencies(["codegraph_mcp"], status)

    def test_required_server_down_raises(self):
        """A down required server must raise RuntimeError."""
        status = {
            "codegraph_mcp": (False, None),
            "jira_mcp": (True, ["tool_b"]),
        }
        with pytest.raises(RuntimeError, match="codegraph_mcp"):
            validate_action_dependencies(["codegraph_mcp"], status)

    def test_multiple_required_servers_down(self):
        """All failing required servers are named in the error."""
        status = {
            "codegraph_mcp": (False, None),
            "jira_mcp": (False, None),
        }
        with pytest.raises(RuntimeError) as exc_info:
            validate_action_dependencies(["codegraph_mcp", "jira_mcp"], status)
        msg = str(exc_info.value)
        assert "codegraph_mcp" in msg
        assert "jira_mcp" in msg

    def test_optional_down_only_warns(self, caplog):
        """An unavailable optional service must not raise."""
        import logging

        caplog.set_level(logging.WARNING)

        status = {
            "codegraph_mcp": (True, ["tool_a"]),
            "jira_mcp": (False, None),
        }
        validate_action_dependencies(["codegraph_mcp"], status)
        assert "jira_mcp" in caplog.text

    def test_required_not_in_status_at_all_raises(self):
        """A server absent from the check results must fail fast."""
        status = {"codegraph_mcp": (True, ["tool_a"])}
        with pytest.raises(RuntimeError, match="jira_mcp"):
            validate_action_dependencies(["jira_mcp"], status)
