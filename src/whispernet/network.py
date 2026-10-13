"""Project-owned two-host network namespaces with UDP-only impairment."""

import os
from pathlib import Path
import signal
import re
import shutil
import subprocess
import time
import uuid

from .core import DATA_PORT


def run(*args):
    return subprocess.run(list(args), check=True, text=True, capture_output=True).stdout.strip()


def await_clock_sync(timeout=60):
    """Keep a cold WSL boot alive until timesyncd has completed its first update."""
    if not all(shutil.which(tool) for tool in ("systemctl", "timedatectl")):
        return {"checked": False, "reason": "systemd time service unavailable"}
    active = subprocess.run(["systemctl", "is-active", "--quiet", "systemd-timesyncd"], capture_output=True, timeout=5)
    if active.returncode:
        return {"checked": False, "reason": "systemd-timesyncd inactive"}
    deadline = time.monotonic() + timeout
    print("Waiting for initial Linux clock synchronization before timing capture...", flush=True)
    while True:
        status = subprocess.run(["timedatectl", "timesync-status", "--no-pager"],
                                env={**os.environ, "LC_ALL": "C"}, text=True, capture_output=True, timeout=5)
        packets = re.search(r"Packet count:\s*(\d+)", status.stdout)
        if status.returncode == 0 and packets and int(packets.group(1)) > 0:
            return {"checked": True, "ntp_packets": int(packets.group(1))}
        if time.monotonic() >= deadline:
            raise TimeoutError("Linux clock has not synchronized; check timedatectl timesync-status before retrying")
        time.sleep(1)


class LabNetwork:
    def __init__(self):
        self.tag = uuid.uuid4().hex[:8]
        self.tx, self.rx = f"wn-{self.tag}-tx", f"wn-{self.tag}-rx"
        self.created = []
        help_result = subprocess.run(["tc", "qdisc", "add", "dev", "lo", "root", "netem", "help"],
                                     text=True, capture_output=True)
        self.seed_supported = "seed" in help_result.stdout + help_result.stderr

    def __enter__(self):
        if os.geteuid() != 0:
            raise PermissionError("Network experiments need root; use the supplied WSL launcher")
        try:
            for ns in (self.tx, self.rx):
                run("ip", "netns", "add", ns)
                self.created.append(ns)
                run("ip", "-n", ns, "link", "set", "lo", "up")
            left, right = f"t{self.tag}", f"r{self.tag}"
            run("ip", "link", "add", left, "type", "veth", "peer", "name", right)
            run("ip", "link", "set", left, "netns", self.tx)
            run("ip", "link", "set", right, "netns", self.rx)
            for ns, dev, address in ((self.tx, left, "10.77.0.1/24"), (self.rx, right, "10.77.0.2/24")):
                run("ip", "-n", ns, "link", "set", dev, "name", "eth0")
                run("ip", "-n", ns, "addr", "add", address, "dev", "eth0")
                run("ip", "-n", ns, "link", "set", "eth0", "up")
            self.command(self.tx, "tc", "qdisc", "add", "dev", "eth0", "root", "handle", "1:", "prio")
            self.command(self.tx, "tc", "qdisc", "add", "dev", "eth0", "parent", "1:3", "handle", "30:", "netem")
            self.command(self.tx, "tc", "filter", "add", "dev", "eth0", "protocol", "ip", "parent", "1:",
                         "prio", "1", "u32", "match", "ip", "protocol", "17", "0xff", "match", "ip", "dport",
                         str(DATA_PORT), "0xffff", "flowid", "1:3")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def command(self, ns, *args):
        return run("ip", "netns", "exec", ns, *args)

    def process(self, ns, args, **kwargs):
        return subprocess.Popen(["ip", "netns", "exec", ns, *args], **kwargs)

    def impair(self, delay_ms, jitter_ms, loss_pct, seed, burst=False):
        if not (0 <= delay_ms <= 100 and 0 <= jitter_ms <= 25 and 0 <= loss_pct <= 10):
            raise ValueError("Impairment outside the supported laboratory range")
        args = ["tc", "qdisc", "change", "dev", "eth0", "parent", "1:3", "handle", "30:", "netem",
                "limit", "10000", "delay", f"{delay_ms}ms", f"{jitter_ms}ms", "distribution", "normal"]
        # gemodel: 0.4% enter bad, 10% leave bad, 50% loss in bad, 0% in good (~1.92% average).
        args += ["loss", "gemodel", "0.4%", "10%", "50%", "0%"] if burst and loss_pct else ["loss", f"{loss_pct}%"]
        if self.seed_supported:
            args += ["seed", str(seed)]
        self.command(self.tx, *args)

    def __exit__(self, *unused):
        for ns in reversed(self.created):
            # Only exact namespace names created by this instance are ever removed.
            subprocess.run(["ip", "netns", "del", ns], capture_output=True)
        self.created.clear()


def stop_process(process, timeout=3):
    if process is not None and process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def await_ready(path: Path, process, timeout=10):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None:
            raise RuntimeError("Receiver exited before readiness; inspect receiver.log")
        if time.monotonic() >= deadline:
            raise TimeoutError("Receiver did not become ready")
        time.sleep(0.02)

