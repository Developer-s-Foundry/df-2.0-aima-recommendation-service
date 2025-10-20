# rules/error_rate_rules.py
from typing import Dict, List
from .base import RulePack

class ServiceErrorRateRulePack(RulePack):
    def __init__(self,
                 warn_threshold: float = 0.01,   # 1%
                 crit_threshold: float = 0.05,   # 5%
                 min_qps_for_signal: float = 5   # avoid noise at very low traffic
                 ):
        self.warn = warn_threshold
        self.crit = crit_threshold
        self.min_qps = min_qps_for_signal

    def supports(self, event_type: str) -> bool:
        return event_type in ("service.error_rate", "api.error_rate")

    def evaluate(self, event: Dict) -> List[str]:
        m = event.get("metrics", {}) or {}
        err = m.get("error_rate")
        qps = m.get("qps")
        recos: List[str] = []

        if err is None:
            return ["Error rate metric missing: error_rate."]

        pct = err * 100.0
        if qps is not None and qps < self.min_qps and pct < (self.warn * 100):
            recos.append("ℹ️ Low traffic and low error rate; signal is weak.")
            return recos

        if pct >= self.crit * 100:
            recos.append(f"🚨 Error rate critical ({pct:.2f}%). Consider rollback, incident bridge, and SLO review.")
        elif pct >= self.warn * 100:
            recos.append(f"⚠️ Error rate elevated ({pct:.2f}%). Investigate recent deploys, upstreams, and dependency health.")
        else:
            recos.append(f"✅ Error rate healthy ({pct:.2f}%).")

        if qps is not None and qps > 0 and pct >= self.warn * 100:
            recos.append(f"📈 Affected load ≈ {qps:.0f} rps; prioritize hot paths and top failing endpoints.")

        return recos
