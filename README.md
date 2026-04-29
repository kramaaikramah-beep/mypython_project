# Automated Assessment Checker

Trial-ready local assessment review system for checking student submissions and returning the same document with assessor-style feedback embedded directly inside it.

## Project Goal

This project is designed to support assessors by reviewing student assessment files and inserting feedback into the submitted document itself.

The system is intended to identify:

- incorrect or off-task responses,
- insufficient or underdeveloped responses,
- areas that require improvement,
- unanswered questions,
- sections left blank by the student.

The reviewed output is not a separate report. The returned file is the original assessment document with feedback added at the relevant points, so it can be used immediately by an assessor.

## Current Trial Scope

This build now works as a dynamic assignment reviewer.

It does not depend on preloaded unit JSON files anymore. The system detects question sections directly from the uploaded student file and reviews them with the fast local assessor by default. Claude can be selected as an optional richer, slower assessor engine when an Anthropic API key is configured. If an answer sheet is uploaded, it is used as extra comparison context instead of a hard-coded local rubric.

## Review Engine

This project supports two review engines:

- fast local assessor review,
- optional Claude assessor review.

The system still returns the student's original document with feedback inserted into that same file. The fast assessor is the recommended default for speed, while Claude can be selected when richer external AI review is needed.

## Supported File Types

The trial currently supports:

- `.docx`
- `.pdf`

### DOCX Output

For Word documents, feedback is inserted as inline assessor feedback paragraphs near the relevant question or answer section.

### PDF Output

For PDF files, feedback is inserted as embedded PDF note annotations near detected question markers.

PDF support is suitable for trial testing, but DOCX gives better control because Word documents preserve editable paragraph structure more reliably than PDFs.

## How Question Reading Works

The system can read question markers and question text from the uploaded document.

It currently detects common formats such as:

```text
Q1
Q1.
Q1:
Question 1
Question 1.
Question 1:
```

It then maps the text after each detected question as the student's answer until the next question is found.

Example supported structure:

```text
Q1. Explain the importance of effective communication in a business environment.

Student answer for Q1...

Q2. Identify common barriers to communication and explain how they can be reduced.

Student answer for Q2...
```

The checker reads the question structure from the uploaded file itself. For the most reliable results, the uploaded document should still use clear labels such as `Q1`, `Q2`, `Question 1`, or `Task 1`.

## What The Checker Looks For

For each detected question, the system checks:

- whether an answer exists,
- whether the answer is blank or contains only placeholder characters,
- whether the answer is too short,
- whether the answer appears unrelated to the question,
- whether the answer covers the expected key points,
- whether the answer needs more explanation or examples.

The feedback is written in a professional assessor style using a consistent structure:

```text
Judgement: [assessment judgement]. [specific issue]. Action required: [clear improvement step].
```

Example:

```text
Assessor feedback: Judgement: Partially met. The answer includes clear message and audience, but it is not developed enough to demonstrate full understanding. Action required: Add specific detail on purpose and professional tone and make the link to the question explicit.
```

## Project Structure

```text
app/
  api/
    main.py
    routes/
      evaluation.py

core/
  analyzer/
    completeness.py
  annotator/
    pdf_comment_writer.py
    word_comment_writer.py
  evaluator/
    evaluator.py
  extractor/
    answer_mapper.py
  parser/
    docx_parser.py
    pdf_parser.py
    structure_detector.py
frontend/
  app.py

services/
  claude_review.py
  pipeline.py

storage/
  uploads/
  outputs/
```

## Main Components

### API

`app/api/routes/evaluation.py`

Handles student-file upload, optional answer-sheet upload, runs the assessment pipeline, and returns the reviewed file directly.

### Pipeline

`services/pipeline.py`

Controls the full review process:

1. Detect file type.
2. Parse document text.
3. Detect question sections from the uploaded document.
4. Map questions to student answers.
5. If an answer sheet is uploaded, map the expected answers from that file.
6. Review each student answer with the selected assessor engine.
7. Insert feedback into the original document.
8. Return the reviewed document.

### Parsers

`core/parser/docx_parser.py`

Reads paragraphs from Word documents.

`core/parser/pdf_parser.py`

Extracts text blocks from PDF files.

### Answer Mapper

`core/extractor/answer_mapper.py`

Finds question markers and maps the student's answer text to each detected question.

### Evaluator

`core/evaluator/evaluator.py`

Performs the local fallback checks when Claude is not configured or unavailable.

### Optional Claude Review

`services/claude_review.py`

Sends the mapped questions and student answers to Anthropic Claude using the Messages API and expects structured JSON back. The returned judgement, issue, and action are then inserted into the same uploaded Word or PDF file.

### Annotators

`core/annotator/word_comment_writer.py`

Adds feedback directly into DOCX files.

`core/annotator/pdf_comment_writer.py`

Adds feedback annotations into PDF files.

## Setup

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the full trial project with one command:

```powershell
python main.py
```

This starts:

- the backend API on `http://127.0.0.1:8000`
- the Streamlit frontend on `http://127.0.0.1:8501`

If you prefer running each service separately:

```powershell
uvicorn app.api.main:app --reload
```

```powershell
streamlit run frontend/app.py
```

Open the Streamlit URL shown in the terminal, upload the student submission, optionally upload the assessor answer sheet, review the summary dashboard, and download the reviewed file.

For a public share link, deploy `frontend/app.py` to Streamlit Community Cloud. The Streamlit app can run the assessment pipeline directly, so a separate FastAPI server is not required for a hosted demo. See `DEPLOYMENT.md`.

To enable Claude review, update `.env` or hosting secrets and set:

```text
ASSESSMENT_REVIEW_PROVIDER=claude
ANTHROPIC_API_KEY=your_key_here
CLAUDE_MODEL=claude-3-5-sonnet-20241022
```

If the Anthropic key is missing or Claude fails, use the fast local review engine.

## API Usage

Endpoint:

```text
POST /evaluate
```

Form field:

```text
file
```

Optional form field:

```text
answer_sheet
```

Accepted file types:

```text
.docx
.pdf
```

The API returns structured review data, including:

- review engine details,
- question-by-question review results,
- trial summary counts,
- a reviewed-file download URL.

## Current Trial Limitations

- Claude review depends on a valid Anthropic API key and network access.
- The local fallback engine is criteria-based rather than a full semantic marker.
- It works best when the uploaded document uses clear question labels such as `Q1`, `Q2`, and `Q3`.
- It does not currently grade with numeric marks.
- PDF annotation is less precise than DOCX insertion because PDFs are not structured like editable Word documents.
- Very weak or poorly structured source documents can reduce question-detection quality.
- If no answer sheet is uploaded, Claude must infer the expected answer quality from the question wording and student response alone.

## Recommended Trial Document Format

For best results, use this structure:

```text
Assessment Title

Q1. Question text here

Student answer here

Q2. Question text here

Student answer here

Q3. Question text here

Student answer here
```

Avoid putting multiple questions and answers in the same paragraph.

## Verification Performed

The current implementation has been smoke-tested for:

- Python compilation,
- DOCX upload and feedback insertion,
- PDF upload and annotation insertion,
- blank answer detection,
- insufficient answer detection,
- off-task answer detection,
- dynamic assessor-style improvement feedback.

## Production Considerations

Before moving from trial to final product, the following should be considered:

- stronger assessor rubric support from uploaded marking guides,
- support for tables and complex Word layouts,
- true Word comment bubbles if required,
- assessor approval workflow,
- export audit logs,
- batch uploads,
- user authentication,
- secure file cleanup,
- configurable feedback tone,
- optional human review before final download.

## Summary

This build provides a dynamic, document-based assessment checker. It reads uploaded student submissions, detects question sections from the file itself, reviews the answers with the selected assessor engine, and returns the same file with professional assessor-style feedback embedded directly in the document.
