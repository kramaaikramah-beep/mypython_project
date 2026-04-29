import re


BLANK_RE = re.compile(r"^[\s._\-\u2013\u2014:;|/\\]*$")
DEFAULT_PREFIX_TEMPLATES = (
    "{id}",
    "{id}.",
    "{id}:",
    "Question {number}",
    "Question {number}.",
    "Question {number}:",
    "Q{number}",
    "Q{number}.",
    "Q{number}:",
)
MARKER_BOUNDARY_RE = re.compile(r"^[\s).:\-–—]*($|\s)")


def _question_number(question_id: str) -> str:
    match = re.search(r"\d+", question_id)
    return match.group(0) if match else question_id.lower()


def _marker_context(question: dict) -> dict:
    qid = question["id"].strip()
    return {
        "id": qid,
        "number": _question_number(qid),
        "question": question.get("question", "").strip(),
    }


def _normalize_markers(values) -> list[str]:
    return [value.strip().lower() for value in values if value and value.strip()]


def build_markers(
    question: dict,
    marker_config: dict | None = None,
    config_key: str = "prefix_templates",
    default_templates=DEFAULT_PREFIX_TEMPLATES,
) -> list[str]:
    marker_config = marker_config or {}
    context = _marker_context(question)
    templates = marker_config.get(config_key, default_templates)
    markers = [template.format(**context) for template in templates]
    markers.extend(question.get("markers", []))
    return _normalize_markers(markers)


def prepare_question_specs(questions, marker_config: dict | None = None) -> list[dict]:
    marker_config = marker_config or {}
    match_question_text = marker_config.get("match_question_text") is not False
    specs = []
    for question in questions:
        question_text = question.get("question", "").strip().lower()
        specs.append(
            {
                "question": question,
                "prefixes": tuple(set(build_markers(question, marker_config, "prefix_templates"))),
                "question_text": question_text,
                "question_excerpt": question_text[:80] if question_text else None,
                "match_question_text": match_question_text,
            }
        )
    return specs


def _matches_question(text: str, spec: dict) -> tuple[bool, str | None]:
    candidate = text.strip().lower()
    if not candidate:
        return False, None

    for prefix in sorted(spec["prefixes"], key=len, reverse=True):
        if candidate.startswith(prefix):
            remainder = candidate[len(prefix) :]
            if MARKER_BOUNDARY_RE.match(remainder):
                return True, prefix

    if not spec["match_question_text"]:
        return False, None

    question_excerpt = spec["question_excerpt"]
    matched = bool(question_excerpt and question_excerpt in candidate)
    return matched, (question_excerpt if matched else None)


def _is_blank_answer(text: str) -> bool:
    return not text.strip() or bool(BLANK_RE.match(text.strip()))


def _extract_inline_answer(text: str, matched_marker: str | None, question: dict, marker_config: dict | None = None) -> str:
    stripped = text.strip()
    if not stripped:
        return ""

    candidate = stripped
    if matched_marker:
        marker = matched_marker.strip().lower()
        lowered = candidate.lower()
        if lowered.startswith(marker):
            candidate = candidate[len(matched_marker):].lstrip(" .:-)\t")
            lowered = candidate.lower()
        question_text = question.get("question", "").strip()
        if question_text and lowered.startswith(question_text.lower()):
            candidate = candidate[len(question_text):].lstrip(" .:-)\t")
    else:
        question_text = question.get("question", "").strip()
        lowered = candidate.lower()
        if question_text and question_text.lower() in lowered:
            split_index = lowered.find(question_text.lower()) + len(question_text)
            candidate = candidate[split_index:].lstrip(" .:-)\t")

    return "" if _is_blank_answer(candidate) else candidate.strip()


def map_answers(blocks, questions, marker_config: dict | None = None):
    question_specs = prepare_question_specs(questions, marker_config)
    question_positions = []
    for block in blocks:
        for spec in question_specs:
            question = spec["question"]
            matched, matched_marker = _matches_question(block.text, spec)
            if matched:
                inline_answer = _extract_inline_answer(block.text, matched_marker, question, marker_config)
                question_positions.append(
                    (
                        block.index,
                        question["id"],
                        matched_marker,
                        block.text.strip(),
                        inline_answer,
                    )
                )
                break

    question_positions.sort()
    answers = {}

    for pos, (start_index, qid, matched_marker, matched_text, inline_answer) in enumerate(question_positions):
        next_start = (
            question_positions[pos + 1][0]
            if pos + 1 < len(question_positions)
            else len(blocks)
        )
        answer_blocks = [
            block
            for block in blocks[start_index + 1 : next_start]
            if not _is_blank_answer(block.text)
        ]
        answer_parts = []
        if inline_answer:
            answer_parts.append(inline_answer)
        answer_parts.extend(block.text.strip() for block in answer_blocks)
        answer = "\n".join(part for part in answer_parts if part).strip()
        answers[qid] = {
            "answer": answer,
            "start_index": start_index,
            "end_index": answer_blocks[-1].index if answer_blocks else start_index,
            "status": "blank" if not answer else "answered",
            "marker_found": True,
            "matched_marker": matched_marker,
            "matched_text": matched_text,
        }

    for question in questions:
        answers.setdefault(
            question["id"],
            {
                "answer": "",
                "start_index": None,
                "end_index": None,
                "status": "missing",
                "marker_found": False,
                "matched_marker": None,
                "matched_text": None,
            },
        )

    return answers
