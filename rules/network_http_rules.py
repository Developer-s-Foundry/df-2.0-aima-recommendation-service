# rules/network_http_rules.py
from typing import Dict, List
from .base import RulePack

class NetworkHttpRulePack(RulePack):
    def __init__(self,
                 p95_warn_ms: int = 500,
                 p95_crit_ms: int = 1000,
                 err5xx_warn: float = 0.01,   # 1%
                 err5xx_crit: float = 0.05    # 5%
                 ):
        self.p95_warn = p95_warn_ms
        self.p95_crit = p95_crit_ms
        self.err_warn = err5xx_warn
        self.err_crit = err5xx_crit

    def supports(self, event_type: str) -> bool:
        return event_type in ("net.http", "gateway.http")

    def evaluate(self, event: Dict) -> List[str]:
        m = event.get("metrics", {}) or {}
        p95 = m.get("p95_ms")
        r5x = m.get("5xx_rate")      # fraction (0.012 = 1.2%)
        rps = m.get("throughput_rps")

        recos: List[str] = []
        missing = []
        if p95 is None: missing.append("p95_ms")
        if r5x is None: missing.append("5xx_rate")
        # throughput_rps is optional

        if missing and len(missing) == 2:
            return [f"Network HTTP metrics missing: {', '.join(missing)}."]

        if p95 is not None:
            if p95 >= self.p95_crit:
                recos.append(f"🚨 p95 latency critical ({p95:.0f} ms). Check upstreams, DB latency, and saturation.")
            elif p95 >= self.p95_warn:
                recos.append(f"⚠️ p95 latency elevated ({p95:.0f} ms). Consider caching, connection pooling, autoscaling.")

        if r5x is not None:
            pct = r5x * 100.0
            if pct >= self.err_crit * 100:
                recos.append(f"🚨 5xx rate critical ({pct:.2f}%). Potential outage; roll back and enable circuit breakers.")
            elif pct >= self.err_warn * 100:
                recos.append(f"⚠️ 5xx rate elevated ({pct:.2f}%). Investigate error spikes and dependency health.")

        if not recos:
            recos.append("✅ Network HTTP within thresholds based on provided metrics.")
        if rps is not None and rps > 0 and p95 is not None and p95 >= self.p95_warn:
            recos.append(f"📈 Throughput ≈ {rps:.0f} rps under elevated latency; consider capacity increase and CDN/cache tuning.")
        return recos
