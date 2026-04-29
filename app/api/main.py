from dotenv import load_dotenv
from fastapi import FastAPI
from app.api.routes.evaluation import router

load_dotenv()

app = FastAPI(
    title="AI Assessment Checker API",
    version="0.1.0",
    description="Trial API for reviewing assessment documents and returning embedded assessor feedback.",
)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
