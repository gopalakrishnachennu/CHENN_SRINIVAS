"""Central OpenAI client wrapper with retry, backoff, and call metrics (Wave 4)."""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from openai import OpenAI

from resume_engine.config import thresholds
from resume_engine.config.settings import (
    DEFAULT_OPENAI_MODEL,
    PROMPT_VERSION,
    load_local_environment,
)

logger = logging.getLogger(__name__)


class LLMErrorClass(str, Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    AUTH = "auth"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


@dataclass
class LLMCallMetrics:
    model: str
    latency_ms: float
    retries: int
    success: bool
    error_class: str | None = None
    error_type: str | None = None
    request_id: str | None = None
    run_id: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    operation: str = "responses.parse"


@dataclass
class LLMClient:
    """
    Production OpenAI wrapper.

    Retries only transient / rate-limit / timeout failures.
    Never retries deterministic validation failures (those are not API errors).
    Never logs API keys or full resume payloads.
    """

    timeout_seconds: float = thresholds.LLM_TIMEOUT_SECONDS
    max_retries: int = thresholds.LLM_MAX_RETRIES
    backoff_base_seconds: float = thresholds.LLM_BACKOFF_BASE_SECONDS
    backoff_max_seconds: float = thresholds.LLM_BACKOFF_MAX_SECONDS
    metrics_log: list[LLMCallMetrics] = field(default_factory=list)
    _client: OpenAI | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._client is None:
            load_local_environment()
            self._client = OpenAI(timeout=self.timeout_seconds)

    @property
    def raw(self) -> OpenAI:
        assert self._client is not None
        return self._client

    def classify_error(self, exc: BaseException) -> LLMErrorClass:
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        status = getattr(exc, "status_code", None)

        if "timeout" in name or "timeout" in message:
            return LLMErrorClass.TIMEOUT
        if "ratelimit" in name or status == 429 or "rate limit" in message:
            return LLMErrorClass.RATE_LIMIT
        if status in {401, 403} or "authentication" in name or "permission" in name:
            return LLMErrorClass.AUTH
        if status in {400, 404, 422} or "badrequest" in name or "invalid" in name:
            return LLMErrorClass.INVALID_REQUEST
        if (
            status in {408, 409, 500, 502, 503, 504}
            or "connection" in name
            or "apierror" in name
            or "internalserver" in name
        ):
            return LLMErrorClass.TRANSIENT
        return LLMErrorClass.UNKNOWN

    def is_retryable(self, error_class: LLMErrorClass) -> bool:
        return error_class in {
            LLMErrorClass.TRANSIENT,
            LLMErrorClass.RATE_LIMIT,
            LLMErrorClass.TIMEOUT,
        }

    def _backoff_seconds(self, attempt: int) -> float:
        # Exponential backoff with light jitter.
        delay = min(
            self.backoff_max_seconds,
            self.backoff_base_seconds * (2**attempt),
        )
        return delay + random.uniform(0, min(0.25, delay * 0.1))

    def _extract_usage(self, response: Any) -> tuple[int | None, int | None, int | None]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None, None, None
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        return input_tokens, output_tokens, total_tokens

    def _extract_request_id(self, response: Any, exc: BaseException | None = None) -> str | None:
        if response is not None:
            for attr in ("id", "request_id", "_request_id"):
                value = getattr(response, attr, None)
                if value:
                    return str(value)
        if exc is not None:
            for attr in ("request_id", "_request_id"):
                value = getattr(exc, attr, None)
                if value:
                    return str(value)
        return None

    def parse(
        self,
        *,
        model: str | None = None,
        input: Any,
        text_format: Any,
        run_id: str | None = None,
        prompt_version: str | None = None,
        operation: str = "responses.parse",
    ) -> Any:
        resolved_model = model or DEFAULT_OPENAI_MODEL
        prompt_ver = prompt_version or PROMPT_VERSION
        attempts = 0
        last_exc: BaseException | None = None

        while attempts <= self.max_retries:
            started = time.perf_counter()
            try:
                response = self.raw.responses.parse(
                    model=resolved_model,
                    input=input,
                    text_format=text_format,
                )
                latency_ms = (time.perf_counter() - started) * 1000.0
                input_tokens, output_tokens, total_tokens = self._extract_usage(response)
                metrics = LLMCallMetrics(
                    model=resolved_model,
                    latency_ms=round(latency_ms, 2),
                    retries=attempts,
                    success=True,
                    request_id=self._extract_request_id(response),
                    run_id=run_id,
                    prompt_version=prompt_ver,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    operation=operation,
                )
                self.metrics_log.append(metrics)
                logger.info(
                    "llm_call success model=%s latency_ms=%.1f retries=%s run_id=%s request_id=%s",
                    metrics.model,
                    metrics.latency_ms,
                    metrics.retries,
                    metrics.run_id,
                    metrics.request_id,
                )
                return response
            except Exception as exc:
                latency_ms = (time.perf_counter() - started) * 1000.0
                error_class = self.classify_error(exc)
                last_exc = exc
                metrics = LLMCallMetrics(
                    model=resolved_model,
                    latency_ms=round(latency_ms, 2),
                    retries=attempts,
                    success=False,
                    error_class=error_class.value,
                    error_type=type(exc).__name__,
                    request_id=self._extract_request_id(None, exc),
                    run_id=run_id,
                    prompt_version=prompt_ver,
                    operation=operation,
                )
                self.metrics_log.append(metrics)
                logger.warning(
                    "llm_call failure class=%s type=%s retries=%s run_id=%s",
                    error_class.value,
                    type(exc).__name__,
                    attempts,
                    run_id,
                )
                if not self.is_retryable(error_class) or attempts >= self.max_retries:
                    raise
                time.sleep(self._backoff_seconds(attempts))
                attempts += 1

        assert last_exc is not None
        raise last_exc

    def latest_metrics(self) -> dict[str, Any] | None:
        if not self.metrics_log:
            return None
        return asdict(self.metrics_log[-1])


def build_llm_client(**kwargs: Any) -> LLMClient:
    return LLMClient(**kwargs)


def new_request_correlation_id() -> str:
    return uuid.uuid4().hex[:12]
