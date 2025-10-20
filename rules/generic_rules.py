# rules/generic_rules.py - add lightweight defaults
import time
from typing import Dict, List
from .base import RulePack

class GenericRulePack(RulePack):
    def __init__(self):
        self.last_seen = {}

    def supports(self, event_type: str) -> bool:
        return True  # fallback

    def evaluate(self, event: Dict) -> List[str]:
        recos: List[str] = []
        et = event.get("type", "unknown")
        res = event.get("resource", "resource")
        m = event.get("metrics", {}) or {}

        if not m:
            recos.append("⚠️ No metrics provided in payload.")
            return recos

        # example: note if nothing actionable matched
        recos.append(f"ℹ️ No specific rule pack matched for '{et}'. Metrics received for {res}.")
        return recos
