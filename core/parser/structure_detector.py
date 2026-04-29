import re

from core.extractor.answer_mapper import prepare_question_specs


GENERIC_QUESTION_PATTERNS = (
    re.compile(r"^(question\s+[a-z0-9]+(?:\.[a-z0-9]+)?[\).:\-]?)\s*", re.IGNORECASE),
    re.compile(r"^(q\s*[a-z0-9]+(?:\.[a-z0-9]+)?[\).:\-]?)\s*", re.IGNORECASE),
    re.compile(r"^(task\s+[a-z0-9]+(?:\.[a-z0-9]+)?[\).:\-]?)\s*", re.IGNORECASE),
    re.compile(r"^(section\s+[a-z0-9]+(?:\.[a-z0-9]+)?[\).:\-]?)\s*", re.IGNORECASE),
    re.compile(r"^([0-9]+(?:\.[0-9]+)?[\).:\-])\s*", re.IGNORECASE),
)


def _normalize_identifier(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().rstrip(".:-)"))


def _extract_number(marker: str, fallback_index: int) -> str:
    match = re.search(r"[a-z0-9]+(?:\.[a-z0-9]+)?", marker, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return str(fallback_index)


def _configured_match(text: str, question_specs: list[dict]) -> tuple[dict | None, str | None]:
    candidate = text.strip().lower()
    for spec in question_specs:
        question = spec["question"]
        for marker in spec["prefixes"]:
            if candidate.startswith(marker):
                return question, marker

        if not spec["match_question_text"]:
            continue

        if spec["question_excerpt"] and spec["question_excerpt"] in candidate:
            return question, spec["question_excerpt"]

    return None, None


def _generic_match(text: str) -> tuple[str | None, str | None, str | None]:
    stripped = text.strip()
    if not stripped:
        return None, None, None

    for pattern in GENERIC_QUESTION_PATTERNS:
        match = pattern.match(stripped)
        if match:
            marker = _normalize_identifier(match.group(1))
            question_text = stripped[match.end() :].strip(" .:-\t") or stripped
            return marker, stripped, question_text
    return None, None, None


def discover_questions(blocks, configured_questions: list[dict] | None = None, marker_config: dict | None = None):
    configured_questions = configured_questions or []
    question_specs = prepare_question_specs(configured_questions, marker_config)
    discovered = []
    seen_indexes = set()
    seen_ids = set()

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        configured_question, configured_marker = _configured_match(
            text,
            question_specs,
        )
        if configured_question:
            question_id = configured_question["id"]
            if question_id in seen_ids:
                continue
            discovered.append(
                {
                    "id": question_id,
                    "question": configured_question.get("question") or text,
                    "markers": configured_question.get("markers", []),
                    "detected_marker": configured_marker,
                    "source_text": text,
                    "start_index": block.index,
                }
            )
            seen_indexes.add(block.index)
            seen_ids.add(question_id)
            continue

        generic_marker, source_text, question_text = _generic_match(text)
        if not generic_marker or block.index in seen_indexes:
            continue

        normalized_id = _normalize_identifier(generic_marker)
        if normalized_id in seen_ids:
            continue

        discovered.append(
            {
                "id": normalized_id,
                "question": question_text or source_text,
                "markers": [normalized_id],
                "detected_marker": normalized_id,
                "source_text": source_text,
                "start_index": block.index,
            }
        )
        seen_indexes.add(block.index)
        seen_ids.add(normalized_id)

    return discovered
