import argparse
import json
import subprocess
import threading
import time
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed

NS = "reactor-monitor"


def cap(cmd: list[str]) -> str:
    p = subprocess.run(cmd, text=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.strip()


def replicas(deploy: str) -> int:
    out = cap(["kubectl", "get", "deploy", "-n", NS, deploy, "-o", "jsonpath={.status.replicas}"])
    try:
        return int(out) if out else 0
    except ValueError:
        return 0


def hpa_line(hpa_name: str) -> str:
    # wide is easiest to read
    return cap(["kubectl", "get", "hpa", "-n", NS, hpa_name, "-o", "wide"])


def deployment_selector(deploy: str) -> str:
    data = json.loads(cap(["kubectl", "get", "deploy", "-n", NS, deploy, "-o", "json"]))
    labels = data.get("spec", {}).get("selector", {}).get("matchLabels", {})
    if not labels:
        raise RuntimeError(f"Deployment '{deploy}' has no matchLabels selector")
    # convert to "k=v,k2=v2"
    return ",".join([f"{k}={v}" for k, v in labels.items()])


def first_pod_for_deploy(deploy: str) -> str:
    sel = deployment_selector(deploy)
    pod = cap(["kubectl", "get", "pods", "-n", NS, "-l", sel, "-o", "jsonpath={.items[0].metadata.name}"])
    if not pod:
        raise RuntimeError(f"No pods found for deployment '{deploy}' (selector: {sel})")
    return pod


def run_exec_cpu_burn(deploy: str, duration: int):
    pod = first_pod_for_deploy(deploy)
    print(f"[exec] pod: {pod}")
    cmd = f"end=$((SECONDS+{duration})); while [ $SECONDS -lt $end ]; do :; done"
    # blocks until done
    _ = cap(["kubectl", "exec", "-n", NS, pod, "--", "sh", "-c", cmd])


def http_worker(url: str, stop_at: float) -> int:
    ok = 0
    req = Request(url, headers={"User-Agent": "hpa-demo"})
    while time.time() < stop_at:
        try:
            with urlopen(req, timeout=3) as r:
                _ = r.read(16)
            ok += 1
        except Exception:
            pass
    return ok


def run_http_load(url: str, duration: int, concurrency: int) -> int:
    stop_at = time.time() + duration
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(http_worker, url, stop_at) for _ in range(concurrency)]
        total = 0
        for f in as_completed(futures):
            total += f.result()
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["exec", "http"], default="exec")
    ap.add_argument("--duration", type=int, default=90)
    ap.add_argument("--interval", type=int, default=5)

    ap.add_argument("--deploy", default="controller")
    ap.add_argument("--hpa", default="controller-hpa")

    ap.add_argument("--url", default="http://localhost:8083/health/live")
    ap.add_argument("--concurrency", type=int, default=60)

    args = ap.parse_args()

    print("namespace:", NS)
    print("deploy:", args.deploy)
    print("hpa:", args.hpa)
    print("replicas (before):", replicas(args.deploy))
    print(hpa_line(args.hpa))

    stop_at = time.time() + args.duration

    if args.mode == "exec":
        done = {"ok": False}

        def _run():
            run_exec_cpu_burn(args.deploy, args.duration)
            done["ok"] = True

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        while time.time() < stop_at and not done["ok"]:
            time.sleep(args.interval)
            print("\n" + hpa_line(args.hpa))
            print("replicas:", replicas(args.deploy))

        t.join()

    else:
        print(f"[http] {args.concurrency} workers -> {args.url}")
        res = {"count": 0}

        def _run():
            res["count"] = run_http_load(args.url, args.duration, args.concurrency)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        while time.time() < stop_at:
            time.sleep(args.interval)
            print("\n" + hpa_line(args.hpa))
            print("replicas:", replicas(args.deploy))

        t.join()
        print("approx requests:", res["count"])

    print("\nAFTER:")
    print(hpa_line(args.hpa))
    print("replicas (after):", replicas(args.deploy))
    print("Note: scale-down usually takes 1–3 minutes after load stops.")


if __name__ == "__main__":
    raise SystemExit(main())
