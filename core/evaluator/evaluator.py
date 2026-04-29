import re
from functools import lru_cache
from difflib import SequenceMatcher


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "or",
    "should",
    "the",
    "to",
    "with",
}

TERM_ALIASES = {
    "accuracy": {"accurate", "correct", "error", "proofread", "spelling", "grammar"},
    "appropriate format": {"format", "layout", "letter", "email", "memo", "report"},
    "audience": {"reader", "recipient", "stakeholder", "customer", "manager"},
    "clarification": {"clarify", "confirm", "check", "question"},
    "clear message": {"clear", "message", "concise", "understand"},
    "clear structure": {"structure", "organised", "organized", "introduction", "body"},
    "feedback": {"feedback", "response", "reply", "confirmation"},
    "formal tone": {"formal", "professional", "respectful", "polite"},
    "language barriers": {"language", "jargon", "translation", "terminology"},
    "listening": {"listen", "listening", "attention", "active"},
    "professional tone": {"professional", "formal", "respectful", "polite"},
    "purpose": {"purpose", "objective", "aim", "reason"},
}

CANONICAL_SYNONYMS = {
    "audience": {"audience", "reader", "recipient", "stakeholder", "customer", "manager"},
    "purpose": {"purpose", "objective", "aim", "goal", "reason"},
    "professional": {"professional", "formal", "respectful", "polite", "appropriate"},
    "message": {"message", "information", "meaning", "content", "idea"},
    "clarify": {"clarify", "clarification", "confirm", "confirmation", "verify", "check"},
    "feedback": {"feedback", "response", "reply", "followup", "follow-up"},
    "listening": {"listen", "listening", "attention", "active", "understand"},
    "barrier": {"barrier", "obstacle", "issue", "problem", "difficulty"},
    "structure": {"structure", "organize", "organised", "organized", "layout", "format"},
    "accuracy": {"accuracy", "accurate", "correct", "error", "errors", "proofread", "grammar", "spelling"},
    "workplace": {"workplace", "business", "office", "organisation", "organization", "company"},
}


def _normalize_token(token):
    token = token.lower()
    for suffix in ("ation", "ment", "ness", "ingly", "edly", "ing", "edly", "ed", "es", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


CANONICAL_SYNONYM_LOOKUP = {}
for variants in CANONICAL_SYNONYMS.values():
    normalized_variants = {_normalize_token(item) for item in variants}
    for token in normalized_variants:
        CANONICAL_SYNONYM_LOOKUP[token] = normalized_variants


@lru_cache(maxsize=4096)
def _tokens(text):
    return {
        token
        for token in re.findall(r"[a-zA-Z]{3,}", text.lower())
        if token not in STOP_WORDS
    }


def _stem(token):
    return _normalize_token(token)


@lru_cache(maxsize=4096)
def _expanded_tokens(text):
    expanded = set()
    for token in _tokens(text):
        stemmed = _stem(token)
        expanded.add(stemmed)
        expanded |= CANONICAL_SYNONYM_LOOKUP.get(stemmed, set())
    return expanded


@lru_cache(maxsize=4096)
def _split_ideas(text):
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?])\s+|\n+|;\s*", text.strip())
    return [chunk.strip(" -•\t") for chunk in chunks if len(chunk.strip()) >= 8]


@lru_cache(maxsize=8192)
def _phrase_overlap_score(left, right):
    left_tokens = _expanded_tokens(left)
    right_tokens = _expanded_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    lexical_score = overlap / union if union else 0.0
    text_score = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    containment_bonus = 0.0
    if left_tokens and len(left_tokens & right_tokens) >= max(1, len(left_tokens) // 2):
        containment_bonus = 0.12
    return min(1.0, max(lexical_score, text_score * 0.75) + containment_bonus)


def _collect_answer_sheet_points(question):
    answer_sheet = question.get("answer_sheet") or question.get("model_answer") or ""
    sheet_points = _split_ideas(answer_sheet)
    if not sheet_points:
        sheet_points = list(question.get("key_points", []))
    return answer_sheet, sheet_points


def _match_answer_sheet(answer, answer_sheet_points):
    answer_segments = _split_ideas(answer)
    if not answer_segments:
        answer_segments = [answer]

    covered = []
    missing = []
    scores = []

    for point in answer_sheet_points:
        point_score = 0.0
        for segment in answer_segments:
            point_score = max(point_score, _phrase_overlap_score(point, segment))
        scores.append(point_score)
        if point_score >= 0.45:
            covered.append(point)
        else:
            missing.append(point)

    average_score = sum(scores) / len(scores) if scores else 0.0
    return covered, missing, average_score


def _covered_points(answer, key_points):
    answer_tokens = _expanded_tokens(answer)
    covered = []
    missing = []

    for point in key_points:
        point_tokens = _expanded_tokens(point)
        aliases = {_stem(token) for token in TERM_ALIASES.get(point.lower(), set())}
        if not point_tokens and not aliases:
            continue

        point_overlap = point_tokens & answer_tokens
        alias_overlap = aliases & answer_tokens
        # Single-word criteria need an exact hit. Multi-word criteria allow a
        # partial hit because students rarely repeat rubric wording exactly.
        if alias_overlap:
            covered.append(point)
        elif len(point_tokens) == 1 and point_overlap == point_tokens:
            covered.append(point)
        elif len(point_tokens) > 1 and len(point_overlap) / len(point_tokens) >= 0.5:
            covered.append(point)
        else:
            missing.append(point)

    return covered, missing


def _first_sentence(text):
    sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    return sentence[:180].strip()


def _format_points(points, limit=3):
    shown = points[:limit]
    if len(points) > limit:
        return f"{', '.join(shown)}, and related detail"
    return ", ".join(shown)


def _feedback(judgement, issue, action):
    return f"Judgement: {judgement}. {issue} Action required: {action}"


def _result(judgement, issue, action, covered=None, missing=None):
    return {
        "judgement": judgement,
        "issue": issue,
        "action": action,
        "covered_points": covered or [],
        "missing_points": missing or [],
        "feedback": _feedback(judgement, issue, action),
    }


def evaluate_answer(question, answer):
    answer = (answer or "").strip()
    key_points = question.get("key_points", [])
    answer_sheet, answer_sheet_points = _collect_answer_sheet_points(question)
    minimum_words = question.get("minimum_words", 35)
    word_count = len(answer.split())
    task = question.get("question", "the assessment task")

    if not answer:
        return _result(
            "Not yet assessable",
            "No student response has been provided for this section.",
            f"Add a direct answer to '{task}' and cover the expected points before submission.",
        )

    if not key_points and not answer_sheet_points:
        answer_extract = _first_sentence(answer)
        task_overlap = _expanded_tokens(task) & _expanded_tokens(answer)

        if word_count < max(12, minimum_words // 2):
            return _result(
                "Insufficient evidence",
                f"The response is very brief and does not provide enough detail to assess the task properly. Current evidence begins: '{answer_extract}'.",
                "Expand the answer with a clearer explanation, direct response to the question, and a relevant example where possible.",
            )

        if len(task_overlap) < 2 and word_count < minimum_words:
            return _result(
                "Incorrect or off task",
                "The response does not clearly align with the wording of the detected assessment question.",
                "Rewrite the answer so it responds directly to the question shown in the document and explains the point in practical terms.",
            )

        if word_count < minimum_words:
            return _result(
                "Partially met",
                "The response appears relevant, but it needs more development to demonstrate a complete answer.",
                "Add more explanation, practical detail, and an example that shows how the answer applies.",
            )

        return _result(
            "Met",
            "The response appears relevant to the detected question and contains enough detail for trial review.",
            "For a stronger submission, make the answer more explicit and include a concise workplace example or supporting evidence.",
        )

    covered, missing = _covered_points(answer, key_points)
    answer_sheet_covered, answer_sheet_missing, answer_sheet_score = _match_answer_sheet(
        answer, answer_sheet_points
    )
    key_point_ratio = len(covered) / len(key_points) if key_points else 1
    answer_sheet_ratio = (
        len(answer_sheet_covered) / len(answer_sheet_points) if answer_sheet_points else key_point_ratio
    )
    coverage_ratio = (
        (key_point_ratio * 0.4) + (answer_sheet_ratio * 0.6)
        if key_points and answer_sheet_points
        else answer_sheet_ratio if answer_sheet_points
        else key_point_ratio
    )
    answer_extract = _first_sentence(answer)
    task_overlap = _expanded_tokens(task) & _expanded_tokens(answer)

    result_kwargs = {
        "covered": covered,
        "missing": missing,
    }

    def _final_result(judgement, issue, action):
        payload = _result(judgement, issue, action, **result_kwargs)
        payload["answer_sheet_score"] = round(answer_sheet_score, 2)
        payload["answer_sheet_covered_points"] = answer_sheet_covered
        payload["answer_sheet_missing_points"] = answer_sheet_missing
        payload["answer_sheet_reference"] = answer_sheet
        return payload

    if coverage_ratio < 0.2 and len(task_overlap) < 2:
        expected = _format_points(answer_sheet_points or key_points)
        return _final_result(
            "Incorrect or off task",
            "The response does not appear to address the assessment question or the expected criteria.",
            f"Rewrite this section so it directly explains {expected} in relation to the task.",
        )

    if word_count < max(10, minimum_words // 3) and answer_sheet_score < 0.6:
        expected = _format_points(answer_sheet_points or key_points)
        return _final_result(
            "Insufficient evidence",
            f"The response is very brief and does not provide enough detail to meet the task. Current evidence begins: '{answer_extract}'.",
            f"Expand the answer with a clear explanation of {expected}, using a relevant workplace example where possible.",
        )

    if coverage_ratio < 0.25 and answer_sheet_score < 0.55:
        expected = _format_points(answer_sheet_points or key_points)
        return _final_result(
            "Incorrect or off task",
            "The response does not show enough alignment with the answer sheet or the expected assessment criteria.",
            f"Rewrite this section so it directly explains {expected} in relation to the question.",
        )

    strong_answer_sheet_match = answer_sheet_score >= 0.78 and len(answer_sheet_missing) <= 1
    moderate_answer_sheet_match = answer_sheet_score >= 0.65

    if word_count < minimum_words or coverage_ratio < 0.5:
        if strong_answer_sheet_match and word_count >= max(10, minimum_words // 3):
            return _final_result(
                "Met",
                "The response matches the configured answer sheet closely and addresses the assessment task clearly.",
                "For a stronger submission, add a concise workplace example or a little more supporting detail.",
            )
        if moderate_answer_sheet_match and coverage_ratio >= 0.4:
            return _final_result(
                "Mostly relevant",
                "The response matches much of the expected answer, but it still needs a little more development or precision.",
                "Add a bit more direct detail from the question requirements and include a short example where possible.",
            )
        covered_text = _format_points(covered) if covered else "some relevant ideas"
        if not missing:
            return _final_result(
                "Partially met",
                f"The answer is relevant and includes {covered_text}, but it remains underdeveloped against the expected answer.",
                "Add further explanation, a workplace example, and enough supporting detail to show how the points apply in practice.",
            )
        missing_text = _format_points(answer_sheet_missing or missing)
        return _final_result(
            "Partially met",
            f"The answer includes {covered_text}, but it does not yet match enough of the expected answer content.",
            f"Add specific detail on {missing_text} and make the link to the question explicit.",
        )

    if strong_answer_sheet_match and not answer_sheet_missing:
        return _final_result(
            "Met",
            "The response matches the uploaded answer sheet closely and addresses the assessment task clearly.",
            "For a stronger submission, include a concise workplace example or evidence that shows how the point applies in practice.",
        )

    if answer_sheet_missing or missing:
        missing_text = _format_points(answer_sheet_missing or missing)
        covered_text = _format_points(answer_sheet_covered or covered)
        return _final_result(
            "Mostly relevant",
            f"The response addresses {covered_text}, so it is on the right track.",
            f"Strengthen the answer by also covering {missing_text}; this will make the response more complete against the criteria.",
        )

    return _final_result(
        "Met",
        "The response matches the main answer-sheet expectations and addresses the assessment task clearly.",
        "For a stronger submission, include a concise workplace example or evidence that shows how the point applies in practice.",
    )
