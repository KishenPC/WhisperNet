"""Actual socket integration without namespace privileges or synthetic timestamps."""

import json
import subprocess
import sys

from whispernet.core import to_bytes
from whispernet.network import await_ready, stop_process


def test_real_udp_timing_recovers_unicode_across_frame_boundaries(tmp_path):
    ready = tmp_path / "ready"
    received = tmp_path / "receiver.json"
    sent = tmp_path / "sender.json"
    message = "A\u20acB\U0001f30d"
    receiver = subprocess.Popen([sys.executable, "-m", "whispernet", "receive", "--bind", "127.0.0.1",
                                 "--ready", str(ready), "--output", str(received)])
    try:
        await_ready(ready, receiver)
        subprocess.run([sys.executable, "-m", "whispernet", "send", "--host", "127.0.0.1", "--mode", "fixed",
                        "--message", message, "--output", str(sent)], check=True, timeout=15)
        assert receiver.wait(timeout=5) == 0
        frames = json.loads(received.read_text())["frames"]
        assert all(frame["verified"] for frame in frames)
        assert b"".join(to_bytes(frame["bits"]) for frame in frames).decode("utf-8") == message
        assert [frame["bits"] for frame in frames] == json.loads(sent.read_text())["expected"]
    finally:
        stop_process(receiver)
