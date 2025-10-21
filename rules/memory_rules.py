# rules/memory_rules.py
from typing import Dict, List
from .base import RulePack

class MemoryRulePack(RulePack):
    """
    Rule pack for evaluating memory utilization events.

    Expected schema:
    {
      "type": "system.memory",
      "timestamp": "2025-10-20T09:00:00Z",
      "resource": "host-42",
      "labels": {"os": "windows"},
      "metrics": {"total_gb": 31.9, "free_gb": 6.4}
    }
    """

    def supports(self, event_type: str) -> bool:
        return event_type == "system.memory"

    def evaluate(self, event: Dict) -> List[str]:
        m = event.get("metrics") or {}
        total_gb = m.get("total_gb")
        free_gb  = m.get("free_gb")

        if total_gb is None or free_gb is None:
            return ["⚠️ Memory metrics missing: need total_gb and free_gb."]
        if total_gb <= 0:
            return ["⚠️ Invalid memory size: total_gb must be > 0."]

        used_gb  = total_gb - free_gb
        used_pct = (used_gb / total_gb) * 100.0
        free_pct = 100.0 - used_pct

        recos: List[str] = []
        if used_pct > 85:
            recos.append(
                f"⚠️ High memory usage ({used_pct:.1f}%). "
                "Check for memory leaks, restart runaway services, reduce cache sizes, or add RAM."
            )
        elif used_pct < 20:
            recos.append(
                f"ℹ️ Low memory usage ({used_pct:.1f}%). "
                "System memory is mostly free; consider right-sizing if consistently under-utilized."
            )
        else:
            recos.append(
                f"✅ Memory usage normal ({used_pct:.1f}%, {free_pct:.1f}% free)."
            )

        return recos
