"""Tests for maintenance.reconcile CLI."""

from __future__ import annotations

from resume_engine.maintenance.reconcile import check_integrity, main, repair_integrity
from resume_engine.ui.services.system_service import system_info, workflow_health


def test_reconcile_check_returns_report():
    report = check_integrity()
    assert "jobs_total" in report
    assert "issue_count" in report
    assert "ok" in report
    assert isinstance(report["issues"], list)


def test_reconcile_repair_runs():
    result = repair_integrity()
    assert "after" in result
    assert "fixed" in result


def test_reconcile_cli_check(capsys):
    code = main(["--check"])
    out = capsys.readouterr().out
    assert "jobs_total" in out
    assert code in (0, 1)


def test_system_workflow_health():
    health = workflow_health()
    assert health["river_mode"] == "SHADOW"
    assert "jobs_ready" in health
    info = system_info()
    assert info["integrity"]["river_mode"] == "SHADOW"
    assert info["river_active"] == "OFF"
