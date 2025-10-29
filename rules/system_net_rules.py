# rules/system_net_rules.py
from typing import Dict, List
from .base import RulePack

class SystemNetRulePack(RulePack):
    """
    Supports 'system.net' (host NIC metrics).
    Expected metrics (per event):
      - rx_mbps, tx_mbps
      - rx_err_rate, tx_err_rate (packets/sec)
      - rx_drop_rate, tx_drop_rate (packets/sec)
    """
    def supports(self, event_type: str) -> bool:
        return event_type == "system.net"

    def evaluate(self, event: Dict) -> List[str]:
        m = event.get("metrics", {}) or {}
        labels = event.get("labels", {}) or {}
        nic = labels.get("nic", "unknown")

        rx = m.get("rx_mbps")
        tx = m.get("tx_mbps")
        rx_err = m.get("rx_err_rate")
        tx_err = m.get("tx_err_rate")
        rx_drop = m.get("rx_drop_rate")
        tx_drop = m.get("tx_drop_rate")

        recos: List[str] = []

        # Basic sanity
        if rx is None and tx is None:
            return [f"ℹ️ NIC {nic}: no throughput data."]

        # Throughput thresholds (tune to your NIC capacity; examples here)
        # If your NIC is 100 Mbps, consider >80 Mbps as high. If 1 Gbps, you might set >800 Mbps.
        HIGH_Mbps = 80.0

        if (rx or 0) > HIGH_Mbps or (tx or 0) > HIGH_Mbps:
            recos.append(f"⚠️ NIC {nic}: High throughput (rx {rx:.1f} Mbps, tx {tx:.1f} Mbps). Check link capacity/QoS, consider scaling or traffic split.")

        # Errors & drops are usually 0; any sustained non-zero rate is concerning.
        if (rx_err or 0) > 0 or (tx_err or 0) > 0:
            recos.append(f"⚠️ NIC {nic}: Packet errors detected (rx {rx_err:.4f}/s, tx {tx_err:.4f}/s). Suspect physical link, NIC/driver, or duplex mismatch.")
        if (rx_drop or 0) > 0 or (tx_drop or 0) > 0:
            recos.append(f"⚠️ NIC {nic}: Packet drops observed (rx {rx_drop:.4f}/s, tx {tx_drop:.4f}/s). Check buffers, QoS, and upstream congestion.")

        # If nothing notable, report healthy
        if not recos:
            recos.append(f"✅ NIC {nic}: Network healthy (rx {rx or 0:.2f} Mbps, tx {tx or 0:.2f} Mbps).")

        return recos
