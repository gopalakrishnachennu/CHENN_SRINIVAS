"""OpenAI command center service: routing, telemetry, and cost estimates."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema

MODEL_OPTIONS: list[dict[str, Any]] = [
    {
        "id": "gpt-4.1-nano",
        "label": "GPT-4.1 Nano",
        "tier": "Cheapest / fastest",
        "use": "Best for high-volume JD triage, simple extraction, and low-risk drafts.",
        "input_per_mtok": 0.10,
        "output_per_mtok": 0.40,
    },
    {
        "id": "gpt-4o-mini",
        "label": "GPT-4o Mini",
        "tier": "Cheap legacy small model",
        "use": "Cheap fallback for extraction and simple resume variants if your account still supports it.",
        "input_per_mtok": 0.15,
        "output_per_mtok": 0.60,
    },
    {
        "id": "gpt-4.1-mini",
        "label": "GPT-4.1 Mini",
        "tier": "Low cost balanced",
        "use": "Good budget option for JD analysis and lighter resume generation.",
        "input_per_mtok": 0.40,
        "output_per_mtok": 1.60,
    },
    {
        "id": "gpt-5-nano",
        "label": "GPT-5 Nano",
        "tier": "Cheap current reasoning",
        "use": "Low-cost current-generation option if enabled for your API project.",
        "input_per_mtok": None,
        "output_per_mtok": None,
    },
    {
        "id": "gpt-5-mini",
        "label": "GPT-5 Mini",
        "tier": "Budget current reasoning",
        "use": "Better quality than nano for medium-complexity generation if enabled.",
        "input_per_mtok": None,
        "output_per_mtok": None,
    },
    {
        "id": "gpt-5.6",
        "label": "GPT-5.6 Sol",
        "tier": "Highest quality",
        "use": "Best for final resume generation and difficult JD extraction.",
        "input_per_mtok": 4.00,
        "output_per_mtok": 20.00,
    },
    {
        "id": "gpt-5.6-sol",
        "label": "GPT-5.6 Sol",
        "tier": "Highest quality",
        "use": "Best for final resume generation and difficult JD extraction.",
        "input_per_mtok": 4.00,
        "output_per_mtok": 20.00,
    },
    {
        "id": "gpt-5.6-terra",
        "label": "GPT-5.6 Terra",
        "tier": "Balanced",
        "use": "Balanced default for routine JD analysis.",
        "input_per_mtok": None,
        "output_per_mtok": None,
    },
    {
        "id": "gpt-5.6-luna",
        "label": "GPT-5.6 Luna",
        "tier": "Cost-sensitive",
        "use": "High-volume analysis when quality bar is lower.",
        "input_per_mtok": None,
        "output_per_mtok": None,
    },
    {
        "id": "gpt-5.1",
        "label": "GPT-5.1",
        "tier": "Legacy/current account option",
        "use": "Use only if your account exposes this model.",
        "input_per_mtok": None,
        "output_per_mtok": None,
    },
    {
        "id": "gpt-4.1",
        "label": "GPT-4.1",
        "tier": "Non-reasoning fallback",
        "use": "Structured extraction fallback if configured on your account.",
        "input_per_mtok": None,
        "output_per_mtok": None,
    },
    {
        "id": "gpt-4o",
        "label": "GPT-4o",
        "tier": "Legacy balanced multimodal",
        "use": "Older balanced option; use only if your API project still exposes it.",
        "input_per_mtok": 2.50,
        "output_per_mtok": 10.00,
    },
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _model_price(model: str) -> tuple[float | None, float | None]:
    for option in MODEL_OPTIONS:
        if option["id"] == model:
            return option.get("input_per_mtok"), option.get("output_per_mtok")
    return None, None


def estimate_cost_usd(
    *,
    model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> float | None:
    input_price, output_price = _model_price(model)
    if input_price is None or output_price is None:
        return None
    in_tok = int(input_tokens or 0)
    out_tok = int(output_tokens or 0)
    return round((in_tok / 1_000_000 * input_price) + (out_tok / 1_000_000 * output_price), 6)


def openai_key_status() -> dict[str, Any]:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    configured = bool(key and "PASTE" not in key.upper() and key != "your_real_key_here")
    return {
        "configured": configured,
        "label": "CONFIGURED" if configured else "NOT CONFIGURED",
        "masked": f"{key[:7]}...{key[-4:]}" if configured and len(key) > 14 else None,
    }


def model_options() -> list[dict[str, Any]]:
    return [dict(item) for item in MODEL_OPTIONS]


def record_usage_event(
    *,
    operation: str,
    model: str,
    success: bool,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    latency_ms: float | None = None,
    retries: int | None = None,
    request_id: str | None = None,
    run_id: str | None = None,
    error_class: str | None = None,
    error_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    ensure_ui_schema()
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    cost = estimate_cost_usd(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO openai_usage_events(
              created_at, operation, model, success, input_tokens, output_tokens,
              total_tokens, latency_ms, retries, request_id, run_id,
              error_class, error_type, estimated_cost_usd, metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _now(),
                operation,
                model,
                1 if success else 0,
                input_tokens,
                output_tokens,
                total_tokens,
                latency_ms,
                retries or 0,
                request_id,
                run_id,
                error_class,
                error_type,
                cost,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        conn.commit()


def record_metrics(metrics: Any) -> None:
    payload = asdict(metrics) if is_dataclass(metrics) else dict(metrics)
    record_usage_event(
        operation=payload.get("operation") or "responses.parse",
        model=payload.get("model") or "unknown",
        success=bool(payload.get("success")),
        input_tokens=payload.get("input_tokens"),
        output_tokens=payload.get("output_tokens"),
        total_tokens=payload.get("total_tokens"),
        latency_ms=payload.get("latency_ms"),
        retries=payload.get("retries"),
        request_id=payload.get("request_id"),
        run_id=payload.get("run_id"),
        error_class=payload.get("error_class"),
        error_type=payload.get("error_type"),
        metadata={"prompt_version": payload.get("prompt_version")},
    )


def _window_start(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def usage_summary(*, days: int = 30, limit: int = 25) -> dict[str, Any]:
    ensure_ui_schema()
    since = _window_start(days)
    with connect_ui_db() as conn:
        totals = conn.execute(
            """
            SELECT
              COUNT(*) AS requests,
              SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS successes,
              SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
              COALESCE(SUM(input_tokens), 0) AS input_tokens,
              COALESCE(SUM(output_tokens), 0) AS output_tokens,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
              AVG(latency_ms) AS avg_latency_ms
            FROM openai_usage_events
            WHERE created_at >= ?
            """,
            (since,),
        ).fetchone()
        by_model = conn.execute(
            """
            SELECT model, COUNT(*) AS requests,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
                   SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures
            FROM openai_usage_events
            WHERE created_at >= ?
            GROUP BY model
            ORDER BY requests DESC, model ASC
            """,
            (since,),
        ).fetchall()
        by_operation = conn.execute(
            """
            SELECT operation, COUNT(*) AS requests,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
                   SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures
            FROM openai_usage_events
            WHERE created_at >= ?
            GROUP BY operation
            ORDER BY requests DESC, operation ASC
            """,
            (since,),
        ).fetchall()
        recent = conn.execute(
            """
            SELECT *
            FROM openai_usage_events
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return {
        "days": days,
        "totals": dict(totals or {}),
        "by_model": [dict(row) for row in by_model],
        "by_operation": [dict(row) for row in by_operation],
        "recent": [dict(row) for row in recent],
    }


def usage_for_run(run_id: str | None, *, limit: int = 12) -> dict[str, Any]:
    if not run_id:
        return {
            "totals": {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0},
            "recent": [],
        }
    ensure_ui_schema()
    with connect_ui_db() as conn:
        totals = conn.execute(
            """
            SELECT
              COUNT(*) AS requests,
              SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS successes,
              SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
              COALESCE(SUM(input_tokens), 0) AS input_tokens,
              COALESCE(SUM(output_tokens), 0) AS output_tokens,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
            FROM openai_usage_events
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        recent = conn.execute(
            """
            SELECT *
            FROM openai_usage_events
            WHERE run_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (run_id, limit),
        ).fetchall()
    return {
        "totals": dict(totals or {}),
        "recent": [dict(row) for row in recent],
    }
