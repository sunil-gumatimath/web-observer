"""Correlate every redis connection with its owning Windows process."""
import subprocess

import redis
from dotenv import load_dotenv

load_dotenv(".env")
import os  # noqa: E402

r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

netstat_out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
# map local_port -> pid for any connection to :6379
port_to_pid = {}
for line in netstat_out.splitlines():
    parts = line.split()
    if len(parts) >= 5 and ":6379" in parts[2]:
        local_port = parts[1].rsplit(":", 1)[-1]
        port_to_pid[local_port] = parts[-1]

print(f"{'addr':<22} {'age':>6} {'cmd':<10} {'pid':>7} process")
pid_cache: dict[str, str] = {}
for c in r.client_list():
    addr = c.get("addr", "")
    local_port = addr.rsplit(":", 1)[-1]
    pid = port_to_pid.get(local_port, "?")
    desc = "?"
    if pid != "?":
        if pid not in pid_cache:
            ps = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
                capture_output=True, text=True,
            ).stdout.strip()
            pid_cache[pid] = (ps or "?")[:110]
        desc = pid_cache[pid]
    print(f"{addr:<22} {c.get('age'):>6} {c.get('cmd'):<10} {pid:>7} {desc}")
