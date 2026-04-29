from pathlib import Path
from collections import Counter

from core.annotator.pdf_comment_writer import annotate_pdf
from core.annotator.word_comment_writer import annotate_docx
from core.analyzer.assessor_summary import build_assignment_summary
from core.evaluator.evaluator import evaluate_answer
from core.extractor.answer_mapper import map_answers
from core.parser.docx_parser import parse_docx
from core.parser.pdf_parser import parse_pdf
from core.parser.structure_detector import discover_questions
from services.claude_review import ClaudeReviewError, review_labels, review_submission_with_claude

def _feedback_text(judgement, issue, action):
    return f"Judgement: {judgement}. {issue} Action required: {action}"


def _parse_submission(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    raise ValueError("The trial build supports .docx and .pdf assessment files only.")


def _blocks_to_text(blocks) -> str:
    return "\n".join(block.text.strip() for block in blocks if block.text.strip()).strip()


def _dynamic_question(question_id: str, question_text: str, source_text: str, start_index: int) -> dict:
    return {
        "id": question_id,
        "question": question_text,
        "markers": [question_id, source_text],
        "minimum_words": 35,
        "key_points": [],
        "answer_sheet": "",
        "source_text": source_text,
        "start_index": start_index,
    }


def _single_section_question(blocks, label: str, source_text: str) -> list[dict]:
    start_index = blocks[0].index if blocks else 0
    return [_dynamic_question("Section 1", label, source_text, start_index)]


def _discover_dynamic_questions(blocks, label: str) -> list[dict]:
    discovered_questions = discover_questions(blocks, [], {"match_question_text": False})
    if not discovered_questions:
        fallback_text = blocks[0].text.strip() if blocks else label
        return _single_section_question(blocks, label, fallback_text)

    return [
        _dynamic_question(
            discovered["id"],
            discovered.get("question") or discovered.get("source_text") or label,
            discovered.get("source_text", discovered.get("question", label)),
            discovered.get("start_index", 0),
        )
        for discovered in discovered_questions
    ]


def _map_answers_by_order(blocks, effective_questions):
    discovered_questions = discover_questions(blocks, [], {"match_question_text": False})
    if not discovered_questions:
        return {}

    generic_answers = map_answers(blocks, discovered_questions, {"match_question_text": False})
    ordered_answers = []
    for question in discovered_questions:
        answer = generic_answers.get(question["id"], {}).get("answer", "").strip()
        if answer:
            ordered_answers.append(answer)

    if not ordered_answers:
        return {}

    fallback = {}
    for index, question in enumerate(effective_questions):
        if index >= len(ordered_answers):
            break
        fallback[question["id"]] = ordered_answers[index]
    return fallback


def _map_student_answers(paragraphs, effective_questions):
    if len(effective_questions) == 1 and effective_questions[0]["id"] == "Section 1":
        anchor_index = effective_questions[0].get("start_index", 0)
        answer = _blocks_to_text(paragraphs)
        return {
            "Section 1": {
                "answer": answer,
                "start_index": anchor_index,
                "end_index": paragraphs[-1].index if paragraphs else anchor_index,
                "status": "blank" if not answer else "answered",
                "marker_found": bool(answer),
                "matched_marker": effective_questions[0].get("source_text"),
                "matched_text": effective_questions[0].get("source_text"),
            }
        }

    return map_answers(paragraphs, effective_questions, {"match_question_text": False})


def _merge_uploaded_answer_sheet(answer_sheet_path, effective_questions, marker_config):
    if not answer_sheet_path:
        return effective_questions, {
            "filename": None,
            "source": "ai_dynamic_review",
            "matched_questions": 0,
            "missing_questions": len(effective_questions),
        }

    answer_sheet_blocks = _parse_submission(Path(answer_sheet_path))
    if len(effective_questions) == 1 and effective_questions[0]["id"] == "Section 1":
        merged_question = dict(effective_questions[0])
        merged_question["answer_sheet"] = _blocks_to_text(answer_sheet_blocks)
        return [merged_question], {
            "filename": Path(answer_sheet_path).name,
            "source": "uploaded_answer_sheet",
            "matched_questions": 1 if merged_question["answer_sheet"] else 0,
            "missing_questions": 0 if merged_question["answer_sheet"] else 1,
            "matched_by_order": 0,
        }

    mapped_answers = map_answers(answer_sheet_blocks, effective_questions, marker_config)
    ordered_fallback_answers = _map_answers_by_order(answer_sheet_blocks, effective_questions)
    merged_questions = []
    matched_count = 0
    matched_by_order = 0

    for question in effective_questions:
        sheet_answer = mapped_answers.get(question["id"], {}).get("answer", "").strip()
        if not sheet_answer:
            sheet_answer = ordered_fallback_answers.get(question["id"], "").strip()
        merged_question = dict(question)
        if sheet_answer:
            merged_question["answer_sheet"] = sheet_answer
            matched_count += 1
            if not mapped_answers.get(question["id"], {}).get("answer", "").strip():
                matched_by_order += 1
        merged_questions.append(merged_question)

    total_questions = len(effective_questions)
    if matched_count == 0:
        source = "uploaded_answer_sheet_unmatched"
    elif matched_count < total_questions:
        source = "mixed_uploaded_and_dynamic"
    else:
        source = "uploaded_answer_sheet"

    return merged_questions, {
        "filename": Path(answer_sheet_path).name,
        "source": source,
        "matched_questions": matched_count,
        "missing_questions": max(total_questions - matched_count, 0),
        "matched_by_order": matched_by_order,
    }


def run_pipeline(input_path, output_path, answer_sheet_path=None, review_provider_override=None):
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    paragraphs = _parse_submission(input_path)
    marker_config = {"match_question_text": False}
    effective_questions = _discover_dynamic_questions(paragraphs, "Overall assignment response")
    effective_questions, answer_sheet_info = _merge_uploaded_answer_sheet(
        answer_sheet_path,
        effective_questions,
        marker_config,
    )

    answers = _map_student_answers(paragraphs, effective_questions)
    review_provider, review_provider_label = review_labels(review_provider_override)
    ai_results = None
    review_error = None
    if review_provider == "claude":
        try:
            ai_results = review_submission_with_claude(
                effective_questions,
                answers,
                provider_override=review_provider_override,
            )
            if not ai_results:
                review_provider = "local"
                review_provider_label = "Local fallback review (Claude unavailable)"
                review_error = "Claude did not return assessment results. The app used local rules instead."
        except ClaudeReviewError as exc:
            review_provider = "local"
            review_provider_label = "Local fallback review (Claude fallback)"
            review_error = str(exc)
            ai_results = None
        except Exception as exc:
            review_provider = "local"
            review_provider_label = "Local fallback review (Claude fallback)"
            review_error = f"Unexpected Claude integration error: {exc}"
            ai_results = None

    evaluation_results = {}
    review_items = []

    for q in effective_questions:
        mapped = answers.get(q["id"], {})
        answer = mapped.get("answer", "")
        feedback = ai_results.get(q["id"]) if ai_results else None
        if feedback:
            feedback = {
                **feedback,
                "feedback": _feedback_text(
                    feedback["judgement"],
                    feedback["issue"],
                    feedback["action"],
                ),
            }
        else:
            feedback = evaluate_answer(q, answer)
        judgement = feedback["judgement"]
        word_count = len(answer.split()) if answer else 0
        evaluation_results[q["id"]] = {
            "feedback": feedback["feedback"],
            "anchor_index": mapped.get("end_index") or mapped.get("start_index"),
        }
        review_items.append(
            {
                "question_id": q["id"],
                "question": q.get("question", ""),
                "detected_question_text": q.get("source_text", q.get("question", "")),
                "answer_status": mapped.get("status", "missing"),
                "marker_found": mapped.get("marker_found", False),
                "matched_marker": mapped.get("matched_marker"),
                "matched_text": mapped.get("matched_text"),
                "answer_word_count": word_count,
                "minimum_words": q.get("minimum_words", 0),
                "judgement": judgement,
                "issue": feedback["issue"],
                "action": feedback["action"],
                "feedback": feedback["feedback"],
                "covered_points": feedback["covered_points"],
                "missing_points": feedback["missing_points"],
                "answer_sheet_score": feedback.get("answer_sheet_score", 0.0),
                "answer_sheet_covered_points": feedback.get("answer_sheet_covered_points", []),
                "answer_sheet_missing_points": feedback.get("answer_sheet_missing_points", []),
            }
        )

    judgement_counts = Counter(item["judgement"] for item in review_items)
    answer_status_counts = Counter(item["answer_status"] for item in review_items)
    marker_counts = Counter(bool(item["marker_found"]) for item in review_items)

    if input_path.suffix.lower() == ".pdf":
        annotate_pdf(input_path, output_path, evaluation_results, effective_questions, marker_config)
    else:
        annotate_docx(input_path, output_path, evaluation_results)

    assignment_summary = build_assignment_summary(review_items)

    return {
        "output_path": str(output_path),
        "review_provider": review_provider,
        "review_provider_label": review_provider_label,
        "review_error": review_error,
        "unit_id": None,
        "unit_name": "Dynamic AI assessor review",
        "unit_file": None,
        "answer_sheet_filename": answer_sheet_info["filename"],
        "answer_sheet_source": answer_sheet_info["source"],
        "answer_sheet_questions_matched": answer_sheet_info["matched_questions"],
        "answer_sheet_questions_missing": answer_sheet_info["missing_questions"],
        "answer_sheet_questions_matched_by_order": answer_sheet_info.get("matched_by_order", 0),
        "summary": {
            "total_questions": len(review_items),
            "answered_questions": answer_status_counts.get("answered", 0),
            "blank_questions": answer_status_counts.get("blank", 0),
            "missing_questions": answer_status_counts.get("missing", 0),
            "markers_found": marker_counts.get(True, 0),
            "markers_missing": marker_counts.get(False, 0),
            "met": judgement_counts.get("Met", 0),
            "mostly_relevant": judgement_counts.get("Mostly relevant", 0),
            "partially_met": judgement_counts.get("Partially met", 0),
            "insufficient_evidence": judgement_counts.get("Insufficient evidence", 0),
            "incorrect_or_off_task": judgement_counts.get("Incorrect or off task", 0),
            "not_yet_assessable": judgement_counts.get("Not yet assessable", 0),
        },
        "assignment_summary": assignment_summary,
        "results": review_items,
    }
