"""
Wave 4 infrastructure tests.

Covers LLM client retry/classification/metrics, SQLite LearningRepository,
portable paths, and gitignore privacy policy presence.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from resume_engine.config import thresholds
from resume_engine.config.settings import PROJECT_ROOT, logical_artifact_id, portable_path
from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests
from resume_engine.llm.client import LLMClient, LLMErrorClass

pytestmark = pytest.mark.unit


class _TransientError(Exception):
    status_code = 503


class _RateLimitError(Exception):
    status_code = 429


class _AuthError(Exception):
    status_code = 401


class _BadRequestError(Exception):
    status_code = 400


class _FakeResponses:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        return self.behavior(self.calls, kwargs)


class _FakeOpenAI:
    def __init__(self, behavior):
        self.responses = _FakeResponses(behavior)


def test_llm_classifies_retryable_errors():
    client = LLMClient(_client=_FakeOpenAI(lambda *_: None))
    assert client.classify_error(_TransientError("boom")) == LLMErrorClass.TRANSIENT
    assert client.classify_error(_RateLimitError("slow")) == LLMErrorClass.RATE_LIMIT
    assert client.classify_error(_AuthError("nope")) == LLMErrorClass.AUTH
    assert client.classify_error(_BadRequestError("bad")) == LLMErrorClass.INVALID_REQUEST
    assert client.is_retryable(LLMErrorClass.TRANSIENT)
    assert client.is_retryable(LLMErrorClass.RATE_LIMIT)
    assert not client.is_retryable(LLMErrorClass.AUTH)
    assert not client.is_retryable(LLMErrorClass.INVALID_REQUEST)


def test_llm_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr("resume_engine.llm.client.time.sleep", lambda *_: None)

    def behavior(call_no, _kwargs):
        if call_no < 3:
            raise _TransientError("temporary")
        return SimpleNamespace(
            output_parsed={"ok": True},
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
            id="req_123",
        )

    client = LLMClient(
        _client=_FakeOpenAI(behavior),
        max_retries=3,
        backoff_base_seconds=0.01,
    )
    response = client.parse(
        model="gpt-test",
        input=[{"role": "user", "content": "hi"}],
        text_format=dict,
        run_id="run-x",
        prompt_version="pv",
    )
    assert response.output_parsed == {"ok": True}
    assert client.raw.responses.calls == 3
    metrics = client.latest_metrics()
    assert metrics is not None
    assert metrics["success"] is True
    assert metrics["retries"] == 2
    assert metrics["run_id"] == "run-x"
    assert metrics["request_id"] == "req_123"
    assert metrics["total_tokens"] == 15


def test_llm_does_not_retry_auth_failures(monkeypatch):
    monkeypatch.setattr("resume_engine.llm.client.time.sleep", lambda *_: None)

    def behavior(_call_no, _kwargs):
        raise _AuthError("invalid key")

    client = LLMClient(_client=_FakeOpenAI(behavior), max_retries=3)
    with pytest.raises(_AuthError):
        client.parse(model="gpt-test", input=[], text_format=dict, run_id="r1")
    assert client.raw.responses.calls == 1
    assert client.latest_metrics()["error_class"] == "auth"


def test_learning_repository_sqlite_roundtrip(tmp_path: Path):
    repo = LearningRepository(db_path=tmp_path / "repo.sqlite3", dual_write_jsonl=False)
    repo.save_run(
        {
            "run_id": "run-1",
            "jd_hash": "abc",
            "primary_family": "devops_cloud",
            "secondary_family": "none",
            "seniority": "senior",
            "model": "gpt-test",
            "prompt_version": "pv",
        }
    )
    repo.save_outcome(
        {
            "run_id": "run-1",
            "jd_hash": "abc",
            "variant_id": "V01",
            "variant_positioning": "cloud_infrastructure",
            "primary_family": "devops_cloud",
            "secondary_family": "none",
            "hybrid": False,
            "seniority": "senior",
            "passed": True,
            "score_before": 90.0,
            "score_after": 95.0,
            "eligible_for_learning": True,
        }
    )
    repo.save_failure(
        {
            "run_id": "run-2",
            "jd_hash": "abc",
            "variant_id": "V02",
            "failure_codes": ["FAIL_P4_OVERUSE"],
        }
    )
    repo.save_fingerprint(
        {
            "jd_hash": "abc",
            "run_id": "run-1",
            "variant_id": "V01",
            "passed": True,
            "normalized_text_hash": "deadbeef",
            "text_preview": "preview text",
        }
    )
    history = repo.get_strategy_history(primary_family="devops_cloud", seniority="senior")
    assert len(history) == 1
    assert history[0]["variant_positioning"] == "cloud_infrastructure"
    prior = repo.get_prior_variants("abc")
    assert len(prior) == 1
    assert prior[0]["normalized_text_hash"] == "deadbeef"


def test_outcome_store_dual_writes_jsonl_and_sqlite(tmp_path: Path, monkeypatch):
    from resume_engine.learning import outcome_store
    from resume_engine.learning.outcome_store import save_learning_outcome

    outcomes = tmp_path / "outcomes.jsonl"
    monkeypatch.setattr(outcome_store, "OUTCOMES_FILE", outcomes)
    repo = LearningRepository(db_path=tmp_path / "dual.sqlite3", dual_write_jsonl=True)
    reset_default_repository_for_tests(repo)
    save_learning_outcome(
        {
            "run_id": "dual-1",
            "jd_hash": "hash1",
            "variant_id": "V01",
            "primary_family": "devops_cloud",
            "secondary_family": "none",
            "seniority": "senior",
            "passed": True,
            "eligible_for_learning": True,
            "score_after": 93.0,
        }
    )
    assert outcomes.exists()
    assert "dual-1" in outcomes.read_text(encoding="utf-8")
    history = repo.get_strategy_history(primary_family="devops_cloud")
    assert any(item.get("run_id") == "dual-1" for item in history)
    reset_default_repository_for_tests(None)


def test_portable_path_uses_posix_relative(tmp_path: Path):
    target = PROJECT_ROOT / "resume_engine" / "storage" / "runs" / "demo" / "raw.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}", encoding="utf-8")
    rel = portable_path(target)
    assert rel is not None
    assert not Path(rel).is_absolute()
    assert "Users" not in rel
    assert "\\" not in rel
    assert rel.startswith("resume_engine/storage/runs/")


def test_logical_artifact_id_format():
    artifact = logical_artifact_id("jdhash", "run1", "raw", "V01")
    assert artifact == "runs/jdhash/run1/raw/V01.json"


def test_gitignore_excludes_runtime_storage():
    text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in [
        "resume_engine/storage/runs/",
        "resume_engine/storage/generated/",
        "resume_engine/storage/validated/",
        "resume_engine/storage/rejected/",
        "resume_engine/storage/learning/",
        "resume_engine/storage/reports/",
        "*.sqlite3",
    ]:
        assert pattern in text


def test_llm_constants_present():
    assert thresholds.LLM_MAX_RETRIES >= 1
    assert thresholds.LLM_BACKOFF_BASE_SECONDS > 0
    assert thresholds.LLM_TIMEOUT_SECONDS > 0


def test_runtime_artifacts_doc_exists():
    path = PROJECT_ROOT / "docs" / "RUNTIME_ARTIFACTS.md"
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert "git rm -r --cached" in body
    assert "resume_engine/storage/runs/" in body


def test_ci_workflow_exists_and_skips_live():
    workflow = PROJECT_ROOT / ".github" / "workflows" / "tests.yml"
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")
    assert "3.11" in text and "3.12" in text
    assert "not live" in text
    assert "RUN_LIVE_TESTS" in text
