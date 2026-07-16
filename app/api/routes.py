from fastapi import APIRouter, HTTPException, Response

from app.agent.graph import run_analysis
from app.api import store
from app.api.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


@router.get("/")
def root() -> dict:
    """Friendly landing response so hitting the bare API URL isn't a bare 404."""
    return {
        "service": "e-commerce market analysis agent",
        "docs": "/docs",
        "health": "/health",
        "analyze": "POST /analyze  {\"product\": \"iPhone 15\", \"marketplace\": \"amazon\"}",
        "get_analysis": "GET /analyses/{id}",
    }


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest, response: Response) -> AnalyzeResponse:
    cached = store.get_cached_with_id(req.product, req.marketplace)
    if cached is not None:
        report, analysis_id = cached
        response.headers["X-Cache"] = "HIT"
    else:
        report = run_analysis(req.product, req.marketplace)
        analysis_id = store.save(report)
        response.headers["X-Cache"] = "MISS"
    response.headers["X-Analysis-Id"] = analysis_id
    return report


@router.get("/analyses/{analysis_id}", response_model=AnalyzeResponse)
def get_analysis(analysis_id: str) -> AnalyzeResponse:
    report = store.get(analysis_id)
    if report is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return report
