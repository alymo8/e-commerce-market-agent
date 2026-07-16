from fastapi import APIRouter, HTTPException, Response

from app.agent.graph import run_analysis
from app.api import store
from app.api.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest, response: Response) -> AnalyzeResponse:
    cached = store.get_cached(req.product, req.marketplace)
    report = cached or run_analysis(req.product, req.marketplace)
    analysis_id = store.save(report)
    response.headers["X-Analysis-Id"] = analysis_id
    response.headers["X-Cache"] = "HIT" if cached else "MISS"
    return report


@router.get("/analyses/{analysis_id}", response_model=AnalyzeResponse)
def get_analysis(analysis_id: str) -> AnalyzeResponse:
    report = store.get(analysis_id)
    if report is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return report
