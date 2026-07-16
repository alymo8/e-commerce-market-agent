"""Generate a committed sample report without needing a live LLM.

Run: python sample_reports/generate_sample.py
"""
import json
from unittest.mock import patch

from app.agent import nodes
from app.agent.graph import run_analysis


def _fake(system, user):
    if "normalized_product" in system:
        return {"normalized_product": "iPhone 15", "marketplace": "amazon", "focus": "premium phone"}
    return {
        "summary": "iPhone 15 holds a premium price with strong positive sentiment "
                   "driven by camera and build quality; the price trend is mildly upward.",
        "recommendations": [
            "Maintain premium positioning; sentiment supports the price.",
            "Highlight camera quality in marketing — the top positive theme.",
            "Watch competitor prices; two undercut the listed price.",
        ],
    }


if __name__ == "__main__":
    with patch.object(nodes, "complete_json", _fake):
        report = run_analysis("iPhone 15", "amazon")
    with open("sample_reports/iphone-15.json", "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)
    print("wrote sample_reports/iphone-15.json")
