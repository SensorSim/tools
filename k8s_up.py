import argparse
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

NS = "reactor-monitor"

# service -> preferred local port
FORWARDS = [
    ("sensor-manager", 8081),
    ("archiver", 8082),
    ("controller", 8083),
]

ROOT = Path(__file__).resolve().parents[1]
K8S = ROOT / "infra" / "k8s"
MANIFESTS = ["namespace.yaml", "platform.yaml", "apps.yaml", "hpa.yaml"]


def sh(cmd, check=True):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, text=True, check=check)


def cap(cmd):
    print(">", " ".join(cmd))
    p = subprocess.run(cmd, text=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout


def port_free(p: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", p))
            return True
        except OSError:
            return False


def pick_port(preferred: int) -> int:
    for p in range(preferred, preferred + 200):
        if port_free(p):
            return p
    raise RuntimeError(f"No free local port near {preferred}")


def svc_port(name: str) -> int:
    data = json.loads(cap(["kubectl", "get", "svc", "-n", NS, "-o", "json"]))
    for item in data.get("items", []):
        if item.get("metadata", {}).get("name") == name:
            ports = item.get("spec", {}).get("ports", [])
            if not ports:
                raise RuntimeError(f"Service {name} has no ports")
            p = ports[0].get("port")
            if not isinstance(p, int):
                raise RuntimeError(f"Service {name} port invalid: {p}")
            return p
    raise RuntimeError(f"Service {name} not found in namespace {NS}")


def wait_ready(timeout_s: int):
    sh([
        "kubectl", "wait",
        "--for=condition=Ready",
        "pod", "--all",
        "-n", NS,
        f"--timeout={timeout_s}s",
    ])


def delete_ns():
    sh(["kubectl", "delete", "namespace", NS, "--ignore-not-found=true"], check=False)


def wait_ns_gone(max_s: int = 180):
    for _ in range(max_s):
        if NS not in cap(["kubectl", "get", "ns"]):
            return True
        time.sleep(1)
    return False


def apply_all():
    for f in MANIFESTS:
        path = K8S / f
        if path.exists():
            sh(["kubectl", "apply", "-f", str(path)])
        else:
            print(f"missing: {path}")


def start_pf(service: str, lport: int, sport: int, new_window: bool) -> subprocess.Popen:
    cmd = ["kubectl", "port-forward", "-n", NS, f"svc/{service}", f"{lport}:{sport}"]

    creationflags = 0
    stdout = subprocess.PIPE
    stderr = subprocess.STDOUT

    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # lets us send CTRL_BREAK_EVENT
        if new_window:
            creationflags |= subprocess.CREATE_NEW_CONSOLE
            stdout = None
            stderr = None

    return subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=stderr,
        text=True,
        creationflags=creationflags
    )


def stop_pf(p: subprocess.Popen):
    if p.poll() is not None:
        return

    try:
        if os.name == "nt":
            p.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            p.send_signal(signal.SIGINT)
    except Exception:
        pass

    for _ in range(30):
        if p.poll() is not None:
            return
        time.sleep(0.1)

    try:
        p.terminate()
    except Exception:
        pass

    for _ in range(30):
        if p.poll() is not None:
            return
        time.sleep(0.1)

    try:
        p.kill()
    except Exception:
        pass


def key_q_pressed() -> bool:
    if os.name == "nt":
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            return ch in (b"q", b"Q")
        return False
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete namespace first")
    ap.add_argument("--no-apply", action="store_true", help="skip kubectl apply")
    ap.add_argument("--no-wait", action="store_true", help="skip waiting for pods ready")
    ap.add_argument("--timeout", type=int, default=420, help="seconds for kubectl wait")
    ap.add_argument("--pf-windows", action="store_true", help="open port-forwards in separate windows (Windows)")
    args = ap.parse_args()

    ctx = cap(["kubectl", "config", "current-context"]).strip()
    if not ctx:
        print("kubectl context not set")
        return 1
    print("context:", ctx)

    if args.reset:
        delete_ns()
        wait_ns_gone()

    if not args.no_apply:
        apply_all()

    if not args.no_wait:
        wait_ready(args.timeout)

    procs = []
    urls = []

    for svc, preferred_local in FORWARDS:
        sp = svc_port(svc)
        lp = pick_port(preferred_local)

        print(f"starting port-forward: {svc}  localhost:{lp} -> {sp}")
        p = start_pf(svc, lp, sp, args.pf_windows)
        time.sleep(0.4)

        # if it died immediately, show whatever it printed (only when not using separate windows)
        if p.poll() is not None:
            msg = ""
            if p.stdout:
                try:
                    msg = p.stdout.read() or ""
                except Exception:
                    msg = ""
            print(f"port-forward failed for {svc}\n{msg}")
            for _, pp in procs:
                stop_pf(pp)
            return 2

        procs.append((svc, p))
        urls.append((svc, lp))

    print("\nport-forward up (press q to stop + delete namespace):")
    for svc, lp in urls:
        print(f"  {svc}: http://localhost:{lp}")

    try:
        while True:
            for svc, p in procs:
                if p.poll() is not None:
                    print(f"\nport-forward died: {svc}")
                    raise KeyboardInterrupt

            if key_q_pressed():
                break

            time.sleep(0.15)

    except KeyboardInterrupt:
        pass
    finally:
        print("\nstopping port-forward...")
        for _, p in procs:
            stop_pf(p)

        print("deleting namespace...")
        delete_ns()
        if wait_ns_gone():
            print("done.")
        else:
            print("namespace deletion still in progress (check: kubectl get ns)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
