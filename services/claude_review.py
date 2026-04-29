from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from core.evaluator.evaluator import evaluate_answer


CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
REVIEW_PROVIDER_ENV = "ASSESSMENT_REVIEW_PROVIDER"
CLAUDE_MODEL_ENV = "CLAUDE_MODEL"
ANTHROPIC_MODEL_ENV = "ANTHROPIC_MODEL"
CLAUDE_API_KEY_ENV = "ANTHROPIC_API_KEY"
CLAUDE_TIMEOUT_ENV = "CLAUDE_API_TIMEOUT"
CLAUDE_CONNECT_TIMEOUT_ENV = "CLAUDE_CONNECT_TIMEOUT"
CLAUDE_RETRIES_ENV = "CLAUDE_RETRIES"
CLAUDE_MAX_TOKENS_ENV = "CLAUDE_MAX_TOKENS"
CLAUDE_BATCH_SIZE_ENV = "CLAUDE_REVIEW_BATCH_SIZE"
CLAUDE_FIELD_LIMIT_ENV = "CLAUDE_FIELD_CHAR_LIMIT"
CLAUDE_REVIEW_MODE_ENV = "CLAUDE_REVIEW_MODE"
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_TIMEOUT = 60
DEFAULT_CONNECT_TIMEOUT = 5
DEFAULT_RETRIES = 0
DEFAULT_MAX_TOKENS = 4096
DEFAULT_BATCH_SIZE = 10
DEFAULT_FIELD_LIMIT = 2500
SUPPORTED_JUDGEMENTS = {
    "Met",
    "Mostly relevant",
    "Partially met",
    "Insufficient evidence",
    "Incorrect or off task",
    "Not yet assessable",
}


class ClaudeReviewError(RuntimeError):
    pass


def configured_review_provider() -> str:
    provider = os.getenv(REVIEW_PROVIDER_ENV, "claude").strip().lower()
    if provider in {"local", "claude", "auto"}:
        return provider
    return "claude"


def resolved_review_provider(provider_override: str | None = None) -> str:
    provider = (provider_override or configured_review_provider()).strip().lower()
    if provider == "local":
        return "local"
    if provider not in {"claude", "auto"}:
        provider = configured_review_provider()
    if os.getenv(CLAUDE_API_KEY_ENV, "").strip():
        return "claude"
    return "local"


def review_labels(provider_override: str | None = None) -> tuple[str, str]:
    resolved = resolved_review_provider(provider_override)
    if resolved == "claude":
        return resolved, "Claude assessor"
    return resolved, "Local fallback review"


def _evidence_schema() -> dict[str, Any]:
    item_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "question_id": {"type": "string"},
            "answer_quality": {"type": "string"},
            "relevance_to_question": {"type": "string"},
            "sufficient_detail": {"type": "boolean"},
            "student_answer_summary": {"type": "string"},
            "direct_evidence": {"type": "array", "items": {"type": "string"}},
            "covered_points": {"type": "array", "items": {"type": "string"}},
            "missing_points": {"type": "array", "items": {"type": "string"}},
            "answer_sheet_covered_points": {"type": "array", "items": {"type": "string"}},
            "answer_sheet_missing_points": {"type": "array", "items": {"type": "string"}},
            "answer_sheet_score": {"type": "number"},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "question_id",
            "answer_quality",
            "relevance_to_question",
            "sufficient_detail",
            "student_answer_summary",
            "direct_evidence",
            "covered_points",
            "missing_points",
            "answer_sheet_covered_points",
            "answer_sheet_missing_points",
            "answer_sheet_score",
            "risk_flags",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"results": {"type": "array", "items": item_schema}},
        "required": ["results"],
    }


def _final_schema() -> dict[str, Any]:
    item_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "question_id": {"type": "string"},
            "judgement": {"type": "string"},
            "issue": {"type": "string"},
            "action": {"type": "string"},
            "covered_points": {"type": "array", "items": {"type": "string"}},
            "missing_points": {"type": "array", "items": {"type": "string"}},
            "answer_sheet_score": {"type": "number"},
            "answer_sheet_covered_points": {"type": "array", "items": {"type": "string"}},
            "answer_sheet_missing_points": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "question_id",
            "judgement",
            "issue",
            "action",
            "covered_points",
            "missing_points",
            "answer_sheet_score",
            "answer_sheet_covered_points",
            "answer_sheet_missing_points",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"results": {"type": "array", "items": item_schema}},
        "required": ["results"],
    }


def _evidence_system_prompt() -> str:
    return (
        "You are an experienced assignment assessor performing evidence extraction only. "
        "Read each student answer against the supplied question, minimum words, detected context, and optional answer sheet. "
        "Do not give a final judgement yet. "
        "Extract only evidence that is clearly present in the student answer. "
        "Do not infer unstated competence. Do not reward vague filler. "
        "If the answer is blank, missing, too short, or off task, state that plainly in the evidence fields. "
        "The direct_evidence field must contain short quoted or paraphrased answer fragments grounded in the student response. "
        "Return JSON only."
    )


def _final_system_prompt() -> str:
    return (
        "You are a strict academic assignment assessor making final review decisions from structured evidence. "
        "Use the question details, extracted evidence, and baseline rule-based analysis to decide the final judgement. "
        "Be conservative and evidence-based. "
        "Judgements allowed only: Met, Mostly relevant, Partially met, Insufficient evidence, Incorrect or off task, Not yet assessable. "
        "Calibration rules: "
        "'Met' only if the answer clearly addresses the task, shows sound understanding, covers the main required points, and has enough detail. "
        "'Mostly relevant' only if the answer is on task and substantially correct but still missing limited detail. "
        "'Partially met' if some required content is present but the answer is incomplete or underdeveloped. "
        "'Insufficient evidence' if the answer is too brief, too vague, or too thin to assess properly. "
        "'Incorrect or off task' if the answer mainly fails to address the expected content. "
        "'Not yet assessable' only if there is no real answer. "
        "Issue must state what is wrong or missing in one or two short sentences. "
        "Action must tell the student exactly what to add, explain, compare, justify, or correct. "
        "Write like a human assessor reviewing coursework, not like a generic chatbot. "
        "Do not invent answer content. If the extracted answer appears to include another question, misplaced content, headings only, or template text, identify that risk in the issue/action. "
        "Keep feedback specific to the detected question and the exact submitted answer. "
        "Avoid praise unless the answer substantially meets the task. "
        "Return JSON only."
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ClaudeReviewError("Claude response was empty.")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ClaudeReviewError("Claude response did not contain valid JSON.") from None
        return json.loads(text[start : end + 1])


def _model_name() -> str:
    for env_name in (CLAUDE_MODEL_ENV, ANTHROPIC_MODEL_ENV):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return DEFAULT_MODEL


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _clip_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return (
        text[: limit // 2].rstrip()
        + "\n\n[... middle omitted to keep Claude request focused ...]\n\n"
        + text[-limit // 2 :].lstrip()
    )


def _string_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _chunks(items: list[dict[str, Any]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _call_claude(api_key: str, timeout: int, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = {
        "model": _model_name(),
        "max_tokens": _env_int(CLAUDE_MAX_TOKENS_ENV, DEFAULT_MAX_TOKENS, 1024, 16000),
        "temperature": 0,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=True)}],
            }
        ],
    }

    retries = _env_int(CLAUDE_RETRIES_ENV, DEFAULT_RETRIES, 0, 5)
    connect_timeout = _env_int(
        CLAUDE_CONNECT_TIMEOUT_ENV,
        DEFAULT_CONNECT_TIMEOUT,
        3,
        60,
    )
    last_error: requests.RequestException | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(
                CLAUDE_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
                timeout=(connect_timeout, timeout),
            )
            break
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt >= retries:
                raise ClaudeReviewError(
                    f"Claude request failed after {retries + 1} attempt(s): {exc}"
                ) from exc
            time.sleep(min(2 ** attempt, 8))
        except requests.RequestException as exc:
            raise ClaudeReviewError(f"Claude request failed: {exc}") from exc
    else:
        raise ClaudeReviewError(f"Claude request failed: {last_error}")

    if not response.ok:
        request_id = response.headers.get("request-id")
        detail = response.text.strip()
        try:
            error_payload = response.json()
            detail = (
                error_payload.get("error", {}).get("message")
                or error_payload.get("detail")
                or detail
            )
        except ValueError:
            pass
        if request_id:
            raise ClaudeReviewError(f"Claude API error ({request_id}): {detail}")
        raise ClaudeReviewError(f"Claude API error: {detail}")

    payload = response.json()
    if payload.get("stop_reason") == "max_tokens":
        raise ClaudeReviewError("Claude response was truncated before completing the assessment JSON.")

    content = payload.get("content", [])
    text_parts = [
        part.get("text", "")
        for part in content
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    return _extract_json_object("\n".join(text_parts))


def _repair_claude_json(
    api_key: str,
    timeout: int,
    schema: dict[str, Any],
    expected_ids: set[str],
    raw_payload: dict[str, Any],
    broken_response: dict[str, Any] | None,
) -> dict[str, Any]:
    return _call_claude(
        api_key,
        timeout,
        (
            "You repair assessment JSON. Return valid JSON only. "
            "Keep exactly one result for every expected question_id and use the supplied schema."
        ),
        {
            "task": "Repair or complete the assessment JSON without adding unsupported claims.",
            "schema": schema,
            "expected_question_ids": sorted(expected_ids),
            "original_payload": raw_payload,
            "broken_response": broken_response or {},
        },
    )


def _prepare_review_payload(
    questions: list[dict[str, Any]],
    answers: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    review_payload = []
    field_limit = _env_int(CLAUDE_FIELD_LIMIT_ENV, DEFAULT_FIELD_LIMIT, 1000, 50000)
    for question in questions:
        mapped = answers.get(question["id"], {})
        student_answer = mapped.get("answer", "")
        baseline = evaluate_answer(question, student_answer)
        review_payload.append(
            {
                "question_id": question["id"],
                "question": _clip_text(question.get("question", ""), field_limit),
                "detected_question_text": _clip_text(
                    question.get("source_text", question.get("question", "")),
                    field_limit,
                ),
                "student_answer": _clip_text(student_answer, field_limit),
                "answer_status": mapped.get("status", "missing"),
                "word_count": len((student_answer or "").split()),
                "marker_found": bool(mapped.get("marker_found", False)),
                "matched_marker": mapped.get("matched_marker"),
                "matched_text": _clip_text(mapped.get("matched_text", ""), 1000),
                "minimum_words": question.get("minimum_words", 0),
                "key_points": _string_list(question.get("key_points", []), limit=20),
                "answer_sheet": _clip_text(question.get("answer_sheet", ""), field_limit),
                "baseline_analysis": {
                    "judgement": baseline.get("judgement"),
                    "covered_points": baseline.get("covered_points", []),
                    "missing_points": baseline.get("missing_points", []),
                    "answer_sheet_score": baseline.get("answer_sheet_score", 0.0),
                },
            }
        )
    return review_payload


def _validate_result_ids(results: list[dict[str, Any]], expected_ids: set[str], stage: str) -> None:
    returned_ids = {
        str(item.get("question_id", "")).strip()
        for item in results
        if str(item.get("question_id", "")).strip()
    }
    missing_ids = expected_ids - returned_ids
    if missing_ids:
        raise ClaudeReviewError(
            f"Claude {stage} returned incomplete results. Missing question IDs: {', '.join(sorted(missing_ids))}."
        )


def _coerce_evidence_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": str(item.get("question_id", "")).strip(),
        "answer_quality": str(item.get("answer_quality", "")).strip(),
        "relevance_to_question": str(item.get("relevance_to_question", "")).strip(),
        "sufficient_detail": bool(item.get("sufficient_detail", False)),
        "student_answer_summary": str(item.get("student_answer_summary", "")).strip(),
        "direct_evidence": _string_list(item.get("direct_evidence", [])),
        "covered_points": _string_list(item.get("covered_points", [])),
        "missing_points": _string_list(item.get("missing_points", [])),
        "answer_sheet_covered_points": _string_list(item.get("answer_sheet_covered_points", [])),
        "answer_sheet_missing_points": _string_list(item.get("answer_sheet_missing_points", [])),
        "answer_sheet_score": round(float(item.get("answer_sheet_score", 0.0) or 0.0), 2),
        "risk_flags": _string_list(item.get("risk_flags", [])),
    }


def _normalise_score(value: Any) -> float:
    try:
        score = float(value or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return round(max(0.0, min(1.0, score)), 2)


def _coerce_final_result(item: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    question_id = str(item.get("question_id", "")).strip()
    if not question_id:
        return None

    judgement = str(item.get("judgement", "")).strip()
    if judgement not in SUPPORTED_JUDGEMENTS:
        judgement = "Insufficient evidence"

    return question_id, {
        "judgement": judgement,
        "issue": str(item.get("issue", "")).strip()
        or "The submitted answer does not provide enough clear evidence for this task.",
        "action": str(item.get("action", "")).strip()
        or "Revise the answer so it directly addresses the question with specific, assessable detail.",
        "covered_points": _string_list(item.get("covered_points", []), limit=20),
        "missing_points": _string_list(item.get("missing_points", []), limit=20),
        "answer_sheet_score": _normalise_score(item.get("answer_sheet_score", 0.0)),
        "answer_sheet_covered_points": _string_list(
            item.get("answer_sheet_covered_points", []),
            limit=20,
        ),
        "answer_sheet_missing_points": _string_list(
            item.get("answer_sheet_missing_points", []),
            limit=20,
        ),
    }


def _run_evidence_pass(api_key: str, timeout: int, review_payload: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    all_expected_ids = {item["question_id"] for item in review_payload}
    batch_size = _env_int(CLAUDE_BATCH_SIZE_ENV, DEFAULT_BATCH_SIZE, 1, 10)
    for batch in _chunks(review_payload, batch_size):
        request_payload = {
            "task": (
                "Extract per-question assessment evidence and return JSON only using this schema. "
                "Use answer_sheet_score from 0 to 1. "
                "direct_evidence must contain concise evidence snippets grounded in the student answer."
            ),
            "schema": _evidence_schema(),
            "questions": batch,
        }
        structured = _call_claude(api_key, timeout, _evidence_system_prompt(), request_payload)
        results = structured.get("results", [])
        expected_ids = {item["question_id"] for item in batch}
        try:
            _validate_result_ids(results, expected_ids, "evidence pass")
        except ClaudeReviewError:
            structured = _repair_claude_json(
                api_key,
                timeout,
                _evidence_schema(),
                expected_ids,
                request_payload,
                structured,
            )
            results = structured.get("results", [])
            _validate_result_ids(results, expected_ids, "evidence pass repair")
        for item in results:
            normalised = _coerce_evidence_result(item)
            if normalised["question_id"]:
                normalised["answer_sheet_score"] = _normalise_score(normalised["answer_sheet_score"])
                by_id[normalised["question_id"]] = normalised
    return by_id


def _run_final_pass(
    api_key: str,
    timeout: int,
    review_payload: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    all_expected_ids = {item["question_id"] for item in review_payload}
    final_payload = []
    for item in review_payload:
        final_payload.append(
            {
                **item,
                "evidence_pass": evidence_by_id.get(item["question_id"], {}),
            }
        )

    by_id: dict[str, dict[str, Any]] = {}
    batch_size = _env_int(CLAUDE_BATCH_SIZE_ENV, DEFAULT_BATCH_SIZE, 1, 10)
    for batch in _chunks(final_payload, batch_size):
        request_payload = {
            "task": (
                "Using the extracted evidence and baseline analysis, produce the final assessor review in JSON only. "
                "Keep issue and action concise and assessor-style. "
                "Only mark points as covered when the evidence clearly supports them."
            ),
            "schema": _final_schema(),
            "questions": batch,
        }
        structured = _call_claude(api_key, timeout, _final_system_prompt(), request_payload)
        results = structured.get("results", [])
        expected_ids = {item["question_id"] for item in batch}
        try:
            _validate_result_ids(results, expected_ids, "final pass")
        except ClaudeReviewError:
            structured = _repair_claude_json(
                api_key,
                timeout,
                _final_schema(),
                expected_ids,
                request_payload,
                structured,
            )
            results = structured.get("results", [])
            _validate_result_ids(results, expected_ids, "final pass repair")

        for item in results:
            coerced = _coerce_final_result(item)
            if coerced:
                question_id, feedback = coerced
                by_id[question_id] = feedback

    missing_ids = all_expected_ids - set(by_id)
    if missing_ids:
        raise ClaudeReviewError(
            f"Claude final pass returned invalid or incomplete review results. Missing question IDs: {', '.join(sorted(missing_ids))}."
        )
    return by_id


def _run_quick_final_pass(
    api_key: str,
    timeout: int,
    review_payload: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    all_expected_ids = {item["question_id"] for item in review_payload}
    by_id: dict[str, dict[str, Any]] = {}
    batch_size = _env_int(CLAUDE_BATCH_SIZE_ENV, DEFAULT_BATCH_SIZE, 1, 10)
    for batch in _chunks(review_payload, batch_size):
        request_payload = {
            "task": (
                "Produce the final assessor review directly in JSON only. "
                "Use the student answer, optional answer sheet, and baseline rule-based analysis. "
                "Keep issue/action concise and only mark points as covered when the answer clearly supports them. "
                "This is quick mode, so do not create a separate evidence report."
            ),
            "schema": _final_schema(),
            "questions": batch,
        }
        structured = _call_claude(api_key, timeout, _final_system_prompt(), request_payload)
        results = structured.get("results", [])
        expected_ids = {item["question_id"] for item in batch}
        try:
            _validate_result_ids(results, expected_ids, "quick final pass")
        except ClaudeReviewError:
            structured = _repair_claude_json(
                api_key,
                timeout,
                _final_schema(),
                expected_ids,
                request_payload,
                structured,
            )
            results = structured.get("results", [])
            _validate_result_ids(results, expected_ids, "quick final pass repair")

        for item in results:
            coerced = _coerce_final_result(item)
            if coerced:
                question_id, feedback = coerced
                by_id[question_id] = feedback

    missing_ids = all_expected_ids - set(by_id)
    if missing_ids:
        raise ClaudeReviewError(
            f"Claude quick review returned invalid or incomplete results. Missing question IDs: {', '.join(sorted(missing_ids))}."
        )
    return by_id


def review_submission_with_claude(
    questions: list[dict[str, Any]],
    answers: dict[str, dict[str, Any]],
    provider_override: str | None = None,
) -> dict[str, dict[str, Any]] | None:
    if resolved_review_provider(provider_override) != "claude":
        return None

    api_key = os.getenv(CLAUDE_API_KEY_ENV, "").strip()
    if not api_key:
        return None

    timeout = int(os.getenv(CLAUDE_TIMEOUT_ENV, str(DEFAULT_TIMEOUT)))
    review_payload = _prepare_review_payload(questions, answers)
    review_mode = os.getenv(CLAUDE_REVIEW_MODE_ENV, "quick").strip().lower()
    if review_mode != "detailed":
        return _run_quick_final_pass(api_key, timeout, review_payload)

    evidence_by_id = _run_evidence_pass(api_key, timeout, review_payload)
    return _run_final_pass(api_key, timeout, review_payload, evidence_by_id)
