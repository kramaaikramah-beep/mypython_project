from pydantic import BaseModel, Field


class ReviewItem(BaseModel):
    question_id: str
    question: str
    answer_status: str
    marker_found: bool
    matched_marker: str | None = None
    matched_text: str | None = None
    answer_word_count: int
    minimum_words: int
    judgement: str
    issue: str
    action: str
    feedback: str
    covered_points: list[str]
    missing_points: list[str]
    answer_sheet_score: float = 0.0
    answer_sheet_covered_points: list[str] = []
    answer_sheet_missing_points: list[str] = []


class ReviewSummary(BaseModel):
    total_questions: int
    answered_questions: int
    blank_questions: int
    missing_questions: int
    markers_found: int
    markers_missing: int
    met: int
    mostly_relevant: int
    partially_met: int
    insufficient_evidence: int
    incorrect_or_off_task: int
    not_yet_assessable: int


class AssignmentSummary(BaseModel):
    overall_judgement: str
    readiness: str
    summary_text: str
    completion_rate: int
    pass_rate: int
    total_answer_words: int
    strengths: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)


class EvaluationResponse(BaseModel):
    review_id: str
    original_filename: str
    reviewed_filename: str
    download_url: str
    review_provider: str = "local"
    review_provider_label: str = "Local fallback review"
    review_error: str | None = None
    unit_id: str | None = None
    unit_name: str | None = None
    unit_file: str | None = None
    answer_sheet_filename: str | None = None
    answer_sheet_source: str = "ai_dynamic_review"
    answer_sheet_questions_matched: int = 0
    answer_sheet_questions_missing: int = 0
    answer_sheet_questions_matched_by_order: int = 0
    summary: ReviewSummary
    assignment_summary: AssignmentSummary
    results: list[ReviewItem]
