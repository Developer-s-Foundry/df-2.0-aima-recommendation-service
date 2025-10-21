# rules/disk_rules.py
from typing import Dict, List
from .base import RulePack

class DiskRulePack(RulePack):
    """
    Rule pack for evaluating disk utilization events
    Schema:
      {
        "type": "system.disk",
        "timestamp": "2025-10-20T09:00:00Z",
        "resource": "host-42",
        "labels": {"os": "windows", "volume": "C:"},
        "metrics": {"total_gb": 475.0, "free_gb": 62.3}
      }
    """

    def supports(self, event_type: str) -> bool:
        # Handles only disk-type events
        return event_type == "system.disk"

    def evaluate(self, event: Dict) -> List[str]:
        metrics = event.get("metrics") or {}
        labels = event.get("labels") or {}
        volume = labels.get("volume", "unknown")

        total_gb = metrics.get("total_gb")
        free_gb = metrics.get("free_gb")

        if total_gb is None or free_gb is None:
            return [f"⚠️ Disk metric missing for {volume}: both total_gb and free_gb required."]
        if total_gb <= 0:
            return [f"⚠️ Invalid disk size for {volume}: total_gb must be > 0."]

        used_gb = total_gb - free_gb
        used_pct = (used_gb / total_gb) * 100
        free_pct = 100 - used_pct

        recos: List[str] = []
        if free_pct < 10:
            recos.append(
                f"🚨 Critical: {volume} has only {free_pct:.1f}% free space. "
                f"Immediate cleanup or storage expansion required."
            )
        elif free_pct < 25:
            recos.append(
                f"⚠️ Low free space on {volume} ({free_pct:.1f}% free). "
                f"Plan cleanup or add capacity soon."
            )
        else:
            recos.append(
                f"✅ Disk space healthy on {volume} ({free_pct:.1f}% free)."
            )

        return recos
