import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

from .core import MODES


def main():
    parser = argparse.ArgumentParser(description="WhisperNet controlled network timing laboratory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check dependencies and environment")
    for name in ("demo", "experiment"):
        command = sub.add_parser(name, help="Run actual isolated Linux endpoints and generate results")
        command.add_argument("--output")
        command.add_argument("--duration", type=float, default=8)
        command.add_argument("--repeats", type=int, default=1 if name == "demo" else 3)
        command.add_argument("--scenarios", nargs="+", choices=("clean", "abrupt", "gradual", "burst", "pacing"))
    send = sub.add_parser("send")
    send.add_argument("--host", required=True)
    send.add_argument("--mode", choices=MODES, default="fixed")
    send.add_argument("--message", default="WhisperNet")
    send.add_argument("--duration", type=float, default=0)
    send.add_argument("--seed", type=int, default=1)
    send.add_argument("--output", required=True)
    send.add_argument("--pacing-drift", action="store_true")
    receive = sub.add_parser("receive")
    receive.add_argument("--bind", required=True)
    receive.add_argument("--output", required=True)
    receive.add_argument("--ready", required=True)
    report = sub.add_parser("report", help="Regenerate plots and report from an existing bundle")
    report.add_argument("folder")
    report.add_argument("--recompute-detection", action="store_true", help="Recompute scores from saved, separate benign reference/threshold runs")
    inspect = sub.add_parser("inspect", help="Show experiment measurements")
    inspect.add_argument("folder")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            import numpy, scipy, matplotlib, reportlab
            checks = {"python": sys.version.split()[0], "numpy": numpy.__version__, "scipy": scipy.__version__,
                      "matplotlib": matplotlib.__version__, "reportlab": reportlab.Version, "linux": sys.platform == "linux",
                      "tools": {x: shutil.which(x) for x in ("ip", "tc", "tcpdump", "unshare")},
                      "uid": os.getuid() if hasattr(os, "getuid") else None}
            print(json.dumps(checks, indent=2))
            if not checks["linux"] or not all(checks["tools"].values()):
                return 1
        elif args.command == "send":
            from .endpoint import transmit
            transmit(args.host, args.mode, args.output, args.message, args.duration, args.seed, args.pacing_drift)
        elif args.command == "receive":
            from .endpoint import receive as receiver
            receiver(args.bind, args.output, args.ready)
        elif args.command in ("demo", "experiment"):
            from .experiment import suite
            output = args.output or f"results/{args.command}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            result = suite(output, args.duration, args.repeats, args.scenarios, args.command == "demo")
            Path("results").mkdir(exist_ok=True)
            Path("results/latest.txt").write_text(str(result), encoding="utf-8")
        elif args.command == "report":
            from .report import generate
            if args.recompute_detection:
                from .experiment import evaluate
                from .endpoint import write_json
                path = Path(args.folder) / "summary.json"
                bundle = json.loads(path.read_text())
                bundle["detection"] = evaluate(bundle["runs"], bundle["calibration"])
                write_json(path, bundle)
            generate(args.folder)
        elif args.command == "inspect":
            data = json.loads((Path(args.folder) / "summary.json").read_text())
            for run in data["runs"]:
                print(f"{run['id']}: failure={run['information_failure_rate']} goodput={run['verified_goodput_bps']}")
        return 0
    except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.SubprocessError) as exc:
        print(f"WhisperNet: {exc}", file=sys.stderr)
        return 1

