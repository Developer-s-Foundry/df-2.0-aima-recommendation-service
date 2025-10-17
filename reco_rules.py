# reco_rules.py
def analyze_cpu(cpu_data):
    """
    Takes list of CPU utilization values and returns recommendations.
    cpu_data is a list of floats (percentages).
    """
    recos = []
    if not cpu_data:
        return ["No CPU data received yet."]

    avg_cpu = sum(cpu_data) / len(cpu_data)

    if avg_cpu > 85:
        recos.append(f"⚠️ High average CPU usage ({avg_cpu:.1f}%). Consider scaling up or reducing load.")
    elif avg_cpu < 5:
        recos.append(f"ℹ️ Very low CPU usage ({avg_cpu:.1f}%). System may be idle or under-utilized.")
    else:
        recos.append(f"✅ CPU usage normal ({avg_cpu:.1f}%).")

    return recos

def analyze_memory(mem_total_gb, mem_available_gb):
    """Analyze memory utilization and availability."""
    recos = []
    if not mem_total_gb or not mem_available_gb:
        return ["No memory data received yet."]
    used = mem_total_gb - mem_available_gb
    used_pct = (used / mem_total_gb) * 100

    if used_pct > 85:
        recos.append(f"⚠️ High memory usage ({used_pct:.1f}%). Consider checking memory leaks, restarting services, or adding RAM.")
    elif used_pct < 20:
        recos.append(f"ℹ️ Low memory usage ({used_pct:.1f}%). System memory is mostly free.")
    else:
        recos.append(f"✅ Memory usage normal ({used_pct:.1f}%).")

    return recos


def analyze_disk(disk_total_gb, disk_free_gb, volume="C:"):
    """Analyze disk usage for a specific drive."""
    recos = []
    if not disk_total_gb or not disk_free_gb:
        return [f"No disk data received for volume {volume}."]
    used_gb = disk_total_gb - disk_free_gb
    used_pct = (used_gb / disk_total_gb) * 100

    if used_pct > 90:
        recos.append(f"⚠️ Disk space critically low on {volume} ({100 - used_pct:.1f}% free). Clean up logs, temporary files, or expand storage.")
    elif used_pct > 75:
        recos.append(f"⚠️ Disk usage high on {volume} ({100 - used_pct:.1f}% free). Consider cleanup or adding space.")
    else:
        recos.append(f"✅ Disk space healthy on {volume} ({100 - used_pct:.1f}% free).")

    return recos
