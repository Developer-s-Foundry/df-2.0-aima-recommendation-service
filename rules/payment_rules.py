from typing import Dict, List
from .base import RulePack

class PaymentAPIRulePack(RulePack):
    def supports(self, event_type: str) -> bool:
        return event_type in ("api.payment", "api.checkout")

    def evaluate(self, event: Dict) -> List[str]:
        m = event.get("metrics", {})
        p95 = m.get("p95_ms")
        err = m.get("error_rate")  # fraction e.g. 0.02 = 2%
        qps = m.get("qps")
        recos: List[str] = []

        if p95 is None and err is None:
            return ["Payment metrics missing (p95_ms or error_rate)."]

        if p95 is not None:
            if p95 > 1000:
                recos.append(f"⚠️ High p95 latency ({p95:.0f} ms). Check DB, upstreams, cold starts.")
            elif p95 > 500:
                recos.append(f"⚠️ Elevated p95 latency ({p95:.0f} ms). Watch capacity, cache hit rate.")

        if err is not None:
            pct = err * 100
            if pct > 5:
                recos.append(f"🚨 Error rate critical ({pct:.2f}%). Rollback or open incident.")
            elif pct > 1:
                recos.append(f"⚠️ Error rate elevated ({pct:.2f}%). Investigate recent deploys.")

        if not recos:
            recos.append("✅ Payment API within thresholds.")
        return recos
