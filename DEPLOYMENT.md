# Deployment Guide

## Recommended Share-Link Deployment

Use Streamlit Community Cloud for the fastest public link. The frontend can now run the assessment pipeline directly, so a separate FastAPI server is not required for a simple hosted demo.

### Streamlit Community Cloud

1. Push this project to GitHub.
2. Open Streamlit Community Cloud.
3. Create a new app from the GitHub repository.
4. Set the main file path to:

```text
frontend/app.py
```

5. Add secrets only if you want Claude review:

```toml
ANTHROPIC_API_KEY = "your_key_here"
ASSESSMENT_REVIEW_PROVIDER = "auto"
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
CLAUDE_REVIEW_MODE = "quick"
CLAUDE_API_TIMEOUT = "60"
CLAUDE_CONNECT_TIMEOUT = "5"
CLAUDE_RETRIES = "0"
```

If no Anthropic key is configured, the hosted app still works using the fast local assessor.

## Local Run

For local development with both FastAPI and Streamlit:

```powershell
python main.py
```

For single-app mode, matching hosted deployment:

```powershell
streamlit run frontend/app.py
```

## Notes

- Do not commit `.env` with real API keys.
- Uploaded and reviewed files are written under `storage/uploads` and `storage/outputs`.
- DOCX files give the best feedback placement. PDF feedback works through PDF annotations.
