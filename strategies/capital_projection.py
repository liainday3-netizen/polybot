"""
POLYBOT — Capital Projection Engine
Projects portfolio growth under Conservative / Base / Optimistic ROI scenarios,
compounded monthly. Scenarios are derived from the annualised returns of your
tracked copy-traders:
  Tiger200  ~ 74% annualised (49.5% over 8 months)
  VPenguin  ~ 22% annualised (35.9% over 20 months)
"""
from typing import Any, Dict

SCENARIOS = {
    "conservative": {"label": "Conservative", "color": "#42a5f5", "annual_roi": 0.20},
    "base":         {"label": "Base",          "color": "#7c5cfc", "annual_roi": 0.40},
    "optimistic":   {"label": "Optimistic",    "color": "#00d68f", "annual_roi": 0.70},
}


def _monthly_rate(annual_roi: float) -> float:
    return (1 + annual_roi) ** (1 / 12) - 1


def project(start_capital: float, months: int = 12) -> Dict[str, Any]:
    labels = ["Now"] + [f"M{i}" for i in range(1, months + 1)]
    result: Dict[str, Any] = {
        "start_capital": round(start_capital, 2),
        "months": months,
        "labels": labels,
        "scenarios": {},
        "milestones": {"double": {}, "triple": {}, "ten_x": {}},
    }
    for key, meta in SCENARIOS.items():
        rate = _monthly_rate(meta["annual_roi"])
        values = [round(start_capital * (1 + rate) ** m, 2) for m in range(months + 1)]
        result["scenarios"][key] = {
            "label": meta["label"],
            "color": meta["color"],
            "annual_roi": meta["annual_roi"],
            "values": values,
        }
        for ms_key, mult in [("double", 2), ("triple", 3), ("ten_x", 10)]:
            target = start_capital * mult
            hit = next((m for m, v in enumerate(values) if v >= target), None)
            result["milestones"][ms_key][key] = hit
    return result
