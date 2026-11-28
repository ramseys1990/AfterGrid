"""Read-only, opt-in local AfterGrid resource exercise; no Docker mutations."""
import argparse
import concurrent.futures
import ipaddress
import json
import math
from pathlib import Path
import time
import urllib.request


def private_host(value):
    address = ipaddress.IPv4Address(value)
    if not (address.is_loopback or any(address in ipaddress.IPv4Network(net)
            for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))):
        raise ValueError("Use the local or private IPv4 address of your AfterGrid appliance")
    return str(address)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def sample(url):
    start = time.monotonic()
    try:
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with client.open(url, timeout=5) as response:
            body = response.read(1024 * 1024 + 1)
            ok = response.status == 200 and 0 < len(body) <= 1024 * 1024
            if ok and url.endswith("/health"):
                ok = json.loads(body).get("status") == "ok"
            return ok, time.monotonic() - start, len(body) if ok else 0
    except (OSError, ValueError, AttributeError):
        return False, time.monotonic() - start, 0


def memory_sample(path=Path("/proc/meminfo")):
    try:
        values = {}
        for line in path.read_text().splitlines():
            key, _, value = line.partition(":")
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                values[key] = int(value.split()[0])
        return {"total_kib": values["MemTotal"], "available_kib": values["MemAvailable"],
                "swap_used_kib": values["SwapTotal"] - values["SwapFree"]}
    except (OSError, KeyError, ValueError, IndexError):
        return None


def summarize(rows):
    times = sorted(row[1] for row in rows)
    return {"requests": len(rows), "successful": sum(row[0] for row in rows),
            "bytes": sum(row[2] for row in rows),
            "p95_ms": round(1000 * times[math.ceil(len(times) * .95) - 1], 2) if times else None}


def exercise(host, port=8080, rounds=20, concurrency=4, kiwix=False):
    host = private_host(host)
    if not 1 <= port <= 65535 or not 1 <= rounds <= 100 or not 1 <= concurrency <= 8:
        raise ValueError("Invalid bounded resource exercise settings")
    targets = {"portal_health": f"http://{host}:{port}/health",
               "portal_page": f"http://{host}:{port}/"}
    if kiwix:
        targets["kiwix_reader"] = f"http://{host}:8081/"
    results = {name: [] for name in targets}
    observations = []
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for _ in range(rounds):
            jobs = {pool.submit(sample, url): name for name, url in targets.items()}
            for future in concurrent.futures.as_completed(jobs):
                results[jobs[future]].append(future.result())
            value = memory_sample()
            if value is not None:
                observations.append(value)
            time.sleep(.1)
    return {"target": host, "elapsed_seconds": round(time.monotonic() - started, 2),
            "targets": {name: summarize(rows) for name, rows in results.items()},
            "probe_machine_memory": {"samples": len(observations),
                "min_available_kib": min((x["available_kib"] for x in observations), default=None),
                "max_swap_used_kib": max((x["swap_used_kib"] for x in observations), default=None)},
            "scope": "bounded read-only small-page workload; memory is from the probe machine, not the remote appliance"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="Private appliance IPv4 address")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--kiwix", action="store_true", help="Include installed reader")
    args = parser.parse_args()
    try:
        report = exercise(**vars(args))
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return int(any(row["successful"] != row["requests"] for row in report["targets"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
