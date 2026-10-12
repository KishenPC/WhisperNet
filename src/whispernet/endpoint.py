"""UDP timing data plane and explicit TCP laboratory control plane."""

import json
import math
from pathlib import Path
import random
import selectors
import socket
import struct
import time

from .core import CONTROL_PORT, DATA_PORT, MAGIC, PACKET, PILOT, Timing, checksum, choose_timing, decode_frame, to_bits


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def send_json(sock, value):
    sock.sendall((json.dumps(value, allow_nan=False) + "\n").encode())


def read_json(stream):
    line = stream.readline(65537)
    if not line or len(line) > 65536:
        raise RuntimeError("Control connection closed or message exceeded 64 KiB")
    return json.loads(line)


def receive(bind: str, output: str, ready: str):
    selector = selectors.DefaultSelector()
    frames, arrivals, metadata = [], [], {}
    events = {}
    buffers = {}
    source = "software"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp, socket.socket() as server:
        udp.bind((bind, DATA_PORT))
        udp.setblocking(False)
        try:
            udp.setsockopt(socket.SOL_SOCKET, 35, 1)  # Linux SO_TIMESTAMPNS, including Python builds without its name.
            source = "kernel"
        except OSError:
            pass
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((bind, CONTROL_PORT))
        server.listen(1)
        server.setblocking(False)
        selector.register(udp, selectors.EVENT_READ, "udp")
        selector.register(server, selectors.EVENT_READ, "server")
        Path(ready).write_text("ready", encoding="utf-8")
        done = False
        try:
            while not done:
                selected = selector.select(timeout=30)
                if not selected:
                    raise TimeoutError("Receiver idle for 30 seconds")
                # Drain data before processing a control-plane frame-end marker.
                selected.sort(key=lambda item: item[0].data != "udp")
                for key, _ in selected:
                    sock = key.fileobj
                    if key.data == "server":
                        conn, _ = server.accept()
                        conn.setblocking(False)
                        buffers[conn] = b""
                        selector.register(conn, selectors.EVENT_READ, "control")
                    elif key.data == "udp":
                        while True:
                            try:
                                data, ancillary, _, _ = udp.recvmsg(2048, 128)
                            except BlockingIOError:
                                break
                            timestamp = time.time_ns()
                            for level, kind, value in ancillary:
                                if level == socket.SOL_SOCKET and kind == 35 and len(value) >= 16:
                                    seconds, nanos = struct.unpack("@ll", value[:16])
                                    timestamp = seconds * 1_000_000_000 + nanos
                            if len(data) != PACKET.size:
                                continue
                            magic, frame, index = PACKET.unpack(data)
                            if magic != MAGIC or frame not in metadata:
                                continue
                            event = {"frame": frame, "index": index, "timestamp_ns": timestamp}
                            arrivals.append(event)
                            events[frame].append(event)
                    else:
                        chunk = sock.recv(65536)
                        if not chunk:
                            done = True
                            break
                        buffers[sock] += chunk
                        if len(buffers[sock]) > 65536:
                            raise ValueError("Oversized control message")
                        while b"\n" in buffers[sock]:
                            line, buffers[sock] = buffers[sock].split(b"\n", 1)
                            message = json.loads(line)
                            action = message.get("action")
                            if action == "start":
                                frame = message["frame"]
                                Timing(message["short"], message["long"])
                                if frame != len(metadata) or not (0 < message["payload_bits"] <= 512 and message["payload_bits"] % 8 == 0):
                                    raise ValueError("Invalid frame metadata")
                                metadata[frame] = message
                                events[frame] = []
                                send_json(sock, {"ready": frame})
                            elif action == "end":
                                frame = message["frame"]
                                result = decode_frame(metadata[frame], events[frame])
                                result["start_epoch"] = metadata[frame]["start_epoch"]
                                result["end_epoch"] = time.time()
                                frames.append(result)
                                # Feedback carries estimates and status, never the decoded payload.
                                send_json(sock, {name: result[name] for name in
                                                ("pilot_samples", "raw_sigma", "residual_sigma", "packet_loss_fraction", "verified")})
                            elif action == "finish":
                                send_json(sock, {"finished": True})
                                done = True
                            else:
                                raise ValueError("Unknown control operation")
        finally:
            for conn in buffers:
                conn.close()
            selector.close()
            write_json(output, {"timestamp_source": source, "frames": frames, "arrivals": arrivals})


def transmit(host: str, mode: str, output: str, message: str, duration: float, seed: int, pacing_drift=False):
    if not math.isfinite(duration) or not 0 <= duration <= 120:
        raise ValueError("Duration must be finite and between 0 and 120 seconds")
    rng = random.Random(seed)
    original = message.encode("utf-8")
    if not original or len(original) > 4096:
        raise ValueError("Message must contain 1-4096 UTF-8 bytes")
    chunks = [original[i:i + 4] for i in range(0, len(original), 4)]
    timing, feedback = Timing(), None
    expected, frame_log, sends = [], [], []
    frame, started = 0, time.monotonic()
    with socket.create_connection((host, CONTROL_PORT), timeout=10) as control, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        control.settimeout(15)
        stream = control.makefile("rb")
        while frame < len(chunks) or (duration > 0 and time.monotonic() - started < duration):
            payload = chunks[frame % len(chunks)]
            bits = to_bits(payload)
            timing = choose_timing(mode, feedback, timing)
            meta = {"action": "start", "frame": frame, "payload_bits": len(bits),
                    "crc32": checksum(payload), "short": timing.short, "long": timing.long,
                    "start_epoch": time.time()}
            send_json(control, meta)
            if read_json(stream).get("ready") != frame:
                raise RuntimeError("Receiver failed to acknowledge frame setup")
            sequence = PILOT + bits
            udp.sendto(PACKET.pack(MAGIC, frame, 0), (host, DATA_PORT))
            sends.append({"frame": frame, "index": 0, "epoch_ns": time.time_ns()})
            for index, bit in enumerate(sequence, start=1):
                # Benign traffic is a seeded variable-rate application, not an idle baseline.
                if mode == "benign":
                    age = time.monotonic() - started
                    scale = (.55 if 2 <= age < 5 else 1.5 if age >= 5 else 1) if pacing_drift else 1
                    gap = min(0.160, max(0.002, scale * rng.lognormvariate(-3.775, 0.30)))
                else:
                    gap = timing.gap(bit)
                time.sleep(gap)
                udp.sendto(PACKET.pack(MAGIC, frame, index), (host, DATA_PORT))
                sends.append({"frame": frame, "index": index, "epoch_ns": time.time_ns(), "intended_gap": gap})
            time.sleep(0.180)  # Drain the bounded lab path; overhead is included in goodput.
            send_json(control, {"action": "end", "frame": frame})
            feedback = read_json(stream)
            frame_log.append({**meta, "end_epoch": time.time(), "feedback": feedback})
            expected.append(bits)
            frame += 1
        send_json(control, {"action": "finish"})
        read_json(stream)
    write_json(output, {"mode": mode, "message": message, "seed": seed, "expected": expected,
                        "frames": frame_log, "sends": sends, "elapsed_seconds": time.monotonic() - started})
