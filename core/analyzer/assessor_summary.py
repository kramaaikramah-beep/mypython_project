from __future__ import annotations

from collections import Counter


PASSING_JUDGEMENTS = {"Met", "Mostly relevant"}
ATTENTION_JUDGEMENTS = {
    "Partially met",
    "Insufficient evidence",
    "Incorrect or off task",
    "Not yet assessable",
}


def _clip(value: str, limit: int = 180) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _top_items(items: list[str], limit: int = 4) -> list[str]:
    cleaned = []
    seen = set()
    for item in items:
        text = _clip(item, 140)
        key = text.lower()
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
        if len(cleaned) >= limit:
            break
    return cleaned


def build_assignment_summary(review_items: list[dict]) -> dict:
    total = len(review_items)
    answered = sum(1 for item in review_items if item.get("answer_status") == "answered")
    total_words = sum(int(item.get("answer_word_count") or 0) for item in review_items)
    judgement_counts = Counter(item.get("judgement") for item in review_items)
    needs_attention = [
        item
        for item in review_items
        if item.get("judgement") in ATTENTION_JUDGEMENTS
    ]
    passing_count = sum(judgement_counts.get(judgement, 0) for judgement in PASSING_JUDGEMENTS)
    completion_rate = round((answered / total) * 100) if total else 0
    pass_rate = round((passing_count / total) * 100) if total else 0

    if total == 0:
        overall_judgement = "Not yet assessable"
        readiness = "No assessable questions were detected in the uploaded assignment."
    elif judgement_counts.get("Not yet assessable", 0) == total:
        overall_judgement = "Not yet assessable"
        readiness = "The submission does not contain enough student response evidence to assess."
    elif pass_rate >= 85 and not judgement_counts.get("Incorrect or off task", 0):
        overall_judgement = "Assessment ready"
        readiness = "The submission is mostly complete and ready for assessor review."
    elif pass_rate >= 60:
        overall_judgement = "Needs targeted improvement"
        readiness = "The submission has useful evidence, but some answers need clearer detail before final assessment."
    else:
        overall_judgement = "Needs major revision"
        readiness = "The submission needs substantial improvement before it can be treated as assessment ready."

    strengths = []
    for item in review_items:
        if item.get("judgement") in PASSING_JUDGEMENTS:
            strengths.append(
                f"{item.get('question_id')}: {_clip(item.get('issue') or item.get('feedback') or '')}"
            )

    priority_actions = []
    for item in needs_attention:
        priority_actions.append(
            f"{item.get('question_id')}: {_clip(item.get('action') or 'Revise this answer with more assessable detail.')}"
        )

    if not strengths:
        strengths = ["No strong sections were detected yet. The student should first add clearer, question-specific responses."]
    if not priority_actions:
        priority_actions = ["No urgent correction was detected. A final human assessor should still confirm the evidence against the unit requirements."]

    summary_text = (
        f"The assignment contains {total} detected question(s), with {answered} answered "
        f"and approximately {total_words} student-response words reviewed. "
        f"{passing_count} question(s) are currently Met or Mostly relevant, while "
        f"{len(needs_attention)} question(s) need attention. {readiness}"
    )

    return {
        "overall_judgement": overall_judgement,
        "readiness": readiness,
        "summary_text": summary_text,
        "completion_rate": completion_rate,
        "pass_rate": pass_rate,
        "total_answer_words": total_words,
        "strengths": _top_items(strengths),
        "priority_actions": _top_items(priority_actions),
    }
