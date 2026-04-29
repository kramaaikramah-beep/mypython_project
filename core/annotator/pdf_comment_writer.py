from pathlib import Path

import fitz

from core.extractor.answer_mapper import build_markers


DEFAULT_PDF_SEARCH_TEMPLATES = (
    "{id}",
    "Question {number}",
    "Q{number}",
)


def _search_terms(question: dict, marker_config: dict | None = None) -> list[str]:
    marker_config = marker_config or {}
    search_terms = build_markers(
        question,
        marker_config,
        "pdf_search_templates",
        DEFAULT_PDF_SEARCH_TEMPLATES,
    )
    if search_terms:
        return search_terms
    return build_markers(question, {"prefix_templates": DEFAULT_PDF_SEARCH_TEMPLATES})


def annotate_pdf(
    input_path: str | Path,
    output_path: str | Path,
    evaluation_results,
    questions,
    marker_config: dict | None = None,
):
    question_map = {question["id"]: question for question in questions}

    with fitz.open(str(input_path)) as doc:
        for q_id, result in evaluation_results.items():
            feedback = result.get("feedback", "").strip()
            if not feedback:
                continue

            question = question_map.get(q_id, {"id": q_id, "question": "", "markers": []})
            placed = False
            for page in doc:
                for term in _search_terms(question, marker_config):
                    matches = page.search_for(term)
                    if not matches:
                        continue
                    rect = matches[0]
                    point = fitz.Point(rect.x1 + 12, rect.y0)
                    page.add_text_annot(point, f"Assessor feedback: {feedback}")
                    placed = True
                    break
                if placed:
                    break

            if not placed and len(doc):
                doc[-1].add_text_annot(
                    fitz.Point(36, 36),
                    f"{q_id} - Assessor feedback: {feedback}",
                )

        doc.save(str(output_path))
