from typing import Dict, List, Optional
from .base import RulePack

class CPURulePack(RulePack):
    def supports(self, event_type: str) -> bool:
        return event_type in ("system.cpu", "host.cpu")

    def _get_usage_pct(self, m: Dict) -> Optional[float]:
        """Normalizes various CPU metric shapes to a single percentage."""
        if m is None:
            return None
        if "usage_pct" in m and m["usage_pct"] is not None:
            return float(m["usage_pct"])
        if "used_pct" in m and m["used_pct"] is not None:
            return float(m["used_pct"])
        return None

    def evaluate(self, event: Dict) -> List[str]:
        m = event.get("metrics", {}) or {}
        usage = self._get_usage_pct(m)
        recos: List[str] = []
        if usage is None:
            return ["CPU metric missing: usage_pct/used_pct."]
        if usage > 85:
            recos.append(f"⚠️ High CPU ({usage:.1f}%). Scale up / tune hot paths.")
        elif usage < 5:
            recos.append(f"ℹ️ Very low CPU ({usage:.1f}%). Consider downscaling in off-peak.")
        else:
            recos.append(f"✅ CPU normal ({usage:.1f}%).")
        return recos
