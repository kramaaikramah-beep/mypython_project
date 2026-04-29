from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
import shutil

from app.api.core.evaluation import EvaluationResponse
from services.pipeline import run_pipeline

router = APIRouter()
ROOT_DIR = Path(__file__).resolve().parents[3]
UPLOAD_DIR = ROOT_DIR / "storage" / "uploads"
OUTPUT_DIR = ROOT_DIR / "storage" / "outputs"
ALLOWED_SUFFIXES = {".docx", ".pdf"}


def _find_output(review_id: str) -> Path:
    matches = sorted(OUTPUT_DIR.glob(f"reviewed_{review_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Reviewed file was not found.")
    return matches[0]


def _validate_upload(filename: str, detail: str) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=detail)


def _validate_answer_sheet(filename: str) -> None:
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Answer sheet must be uploaded as a .docx or .pdf file for comparison mode.",
        )


@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate(
    file: UploadFile = File(...),
    answer_sheet: UploadFile | None = File(None),
    review_provider: str = Form("local"),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or "submission.docx").name
    _validate_upload(original_name, "Trial build accepts .docx and .pdf files only.")
    review_provider = review_provider.strip().lower()
    if review_provider not in {"local", "claude"}:
        review_provider = "local"

    answer_sheet_path = None
    answer_sheet_name = None
    if answer_sheet and answer_sheet.filename:
        answer_sheet_name = Path(answer_sheet.filename).name
        _validate_answer_sheet(answer_sheet_name)

    safe_id = uuid4().hex
    input_path = UPLOAD_DIR / f"{safe_id}_{original_name}"
    output_path = OUTPUT_DIR / f"reviewed_{safe_id}_{original_name}"

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if answer_sheet_name:
        answer_sheet_path = UPLOAD_DIR / f"{safe_id}_answersheet_{answer_sheet_name}"
        with open(answer_sheet_path, "wb") as buffer:
            shutil.copyfileobj(answer_sheet.file, buffer)

    try:
        result = run_pipeline(
            input_path,
            output_path,
            answer_sheet_path=answer_sheet_path,
            review_provider_override=review_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Review failed: {exc}") from exc

    return EvaluationResponse(
        review_id=safe_id,
        original_filename=original_name,
        reviewed_filename=f"reviewed_{original_name}",
        download_url=f"/download/{safe_id}",
        review_provider=result.get("review_provider", "local"),
        review_provider_label=result.get("review_provider_label", "Local fallback review"),
        review_error=result.get("review_error"),
        unit_id=result.get("unit_id"),
        unit_name=result.get("unit_name"),
        unit_file=result.get("unit_file"),
        answer_sheet_filename=result.get("answer_sheet_filename"),
        answer_sheet_source=result.get("answer_sheet_source", "ai_dynamic_review"),
        answer_sheet_questions_matched=result.get("answer_sheet_questions_matched", 0),
        answer_sheet_questions_missing=result.get("answer_sheet_questions_missing", 0),
        answer_sheet_questions_matched_by_order=result.get("answer_sheet_questions_matched_by_order", 0),
        summary=result["summary"],
        assignment_summary=result["assignment_summary"],
        results=result["results"],
    )


@router.get("/download/{review_id}")
async def download_review(review_id: str):
    output_path = _find_output(review_id)
    suffix = output_path.suffix.lower()
    media_type = (
        "application/pdf"
        if suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    original_name = output_path.name.split("_", 2)[-1]
    return FileResponse(
        output_path,
        media_type=media_type,
        filename=f"reviewed_{original_name}",
    )
