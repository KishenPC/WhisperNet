"""Run actual endpoints, packet captures and scheduled network impairment."""

import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import threading
import time

from .core import DATA_PORT, metrics, to_bytes
from .detection import Detector, pcap_times, roc, windows
from .endpoint import write_json
from .network import LabNetwork, await_ready, run, stop_process

SCENARIOS = {
    "clean": [(0, 4, .5, 0, False)],
    "abrupt": [(0, 4, .5, 0, False), (2, 40, 8, 2, False), (5, 4, .5, 0, False)],
    "gradual": [(0, 4, .5, 0, False), (2, 20, 3, 0, False), (4, 30, 6, 1, False), (6, 40, 8, 2, False)],
    "burst": [(0, 4, .5, 0, False), (2, 40, 8, 2, True), (5, 4, .5, 0, False)],
    "pacing": [(0, 4, .5, 0, False)],
}


def trial(network, folder, mode, scenario, seed, duration, message="WhisperNet"):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    receiver = sender = capture = None
    halt = threading.Event()
    transitions, failures = [], []
    plan = SCENARIOS[scenario]
    try:
        with (folder / "receiver.log").open("w") as rx_log, (folder / "capture.log").open("w") as cap_log:
            receiver = network.process(network.rx, [sys.executable, "-m", "whispernet", "receive", "--bind", "10.77.0.2",
                                                    "--output", str(folder / "receiver.json"), "--ready", str(folder / "ready")],
                                       stdout=rx_log, stderr=subprocess.STDOUT)
            await_ready(folder / "ready", receiver)
            capture = network.process(network.rx, ["tcpdump", "-i", "eth0", "--immediate-mode", "-U", "-n", "-s", "128",
                                                   "-w", str(folder / "traffic.pcap"), "udp", "dst", "port", str(DATA_PORT)],
                                      stdout=cap_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 5
            while "listening on" not in (folder / "capture.log").read_text():
                if capture.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Packet capture could not start; inspect capture.log")
                time.sleep(.02)
            network.impair(*plan[0][1:4], seed, burst=plan[0][4])
            origin_monotonic, origin_epoch = time.monotonic(), time.time()
            transitions.append({"offset": 0, "epoch": origin_epoch, "delay_ms": plan[0][1],
                                "jitter_ms": plan[0][2], "loss_pct": plan[0][3], "burst": plan[0][4]})

            def change_conditions():
                for index, (offset, delay, jitter, loss, burst) in enumerate(plan[1:], 1):
                    if halt.wait(max(0, origin_monotonic + offset - time.monotonic())):
                        return
                    try:
                        network.impair(delay, jitter, loss, seed + index, burst=burst)
                        transitions.append({"offset": time.monotonic() - origin_monotonic, "epoch": time.time(),
                                            "delay_ms": delay, "jitter_ms": jitter, "loss_pct": loss, "burst": burst})
                    except Exception as exc:
                        failures.append(str(exc))
                        return

            scheduler = threading.Thread(target=change_conditions, daemon=True)
            scheduler.start()
            with (folder / "sender.log").open("w") as tx_log:
                sender_args = [sys.executable, "-m", "whispernet", "send", "--host", "10.77.0.2",
                                                     "--mode", mode, "--output", str(folder / "sender.json"), "--message", message,
                                                     "--duration", str(duration), "--seed", str(seed)]
                if scenario == "pacing" and mode == "benign":
                    sender_args.append("--pacing-drift")
                sender = network.process(network.tx, sender_args,
                                         stdout=tx_log, stderr=subprocess.STDOUT)
                sender.wait(timeout=max(30, duration * 3 + 20))
            halt.set()
            scheduler.join(timeout=3)
            if sender.returncode:
                raise RuntimeError(f"Sender failed in {folder.name}; inspect sender.log")
            receiver.wait(timeout=5)
            if receiver.returncode:
                raise RuntimeError("Receiver failed; inspect receiver.log")
            if failures:
                raise RuntimeError("Impairment scheduler failed: " + failures[0])
            stop_process(capture)
        sent = json.loads((folder / "sender.json").read_text())
        received = json.loads((folder / "receiver.json").read_text())
        result = metrics(sent["expected"], received["frames"], sent["elapsed_seconds"])
        chunks = (len(message.encode("utf-8")) + 3) // 4
        first_cycle = received["frames"][:chunks]
        recovered = None
        if mode != "benign" and len(first_cycle) == chunks and all(f["verified"] for f in first_cycle):
            recovered = b"".join(to_bytes(f["bits"]) for f in first_cycle).decode("utf-8", errors="replace")
        result["recovered_first_message"] = recovered
        if mode == "benign":
            # Benign data is not a timing-encoded message: BER/goodput are not applicable.
            for key in ("conditional_ber", "substitution_rate", "erasure_rate", "information_failure_rate",
                        "verified_goodput_bps", "raw_information_rate_bps", "frame_success_rate"):
                result[key] = None
        observed = pcap_times(folder / "traffic.pcap")
        capture_stats = (folder / "capture.log").read_text()
        dropped = re.search(r"(\d+) packets dropped by kernel", capture_stats)
        if dropped is None or int(dropped.group(1)) != 0 or len(observed) != len(received["arrivals"]):
            raise RuntimeError(f"Incomplete capture in {folder.name}; PCAP/receiver counts must match with zero capture drops")
        result.update({"id": folder.name, "mode": mode, "scenario": scenario, "seed": seed,
                       "start_epoch": origin_epoch, "transitions": transitions,
                       "timestamp_source": received["timestamp_source"], "captured_packets": len(observed),
                       "capture_windows": windows(observed), "frame_results": received["frames"],
                       "netem_seed_supported": network.seed_supported,
                       "capture_receiver_packet_difference": len(observed) - len(received["arrivals"])})
        result["application_pacing_changes"] = ([{"offset_from_sender_start": 2, "gap_multiplier": .55},
                                                   {"offset_from_sender_start": 5, "gap_multiplier": 1.5}]
                                                  if mode == "benign" and scenario == "pacing" else [])
        recovery = []
        for index, change in enumerate(transitions[1:], 1):
            end = transitions[index + 1]["epoch"] if index + 1 < len(transitions) else float("inf")
            after = [f for f in received["frames"] if f["start_epoch"] >= change["epoch"] and f["end_epoch"] < end]
            pair = next((after[i + 1]["end_epoch"] for i in range(len(after) - 1)
                         if after[i]["verified"] and after[i + 1]["verified"]), None)
            recovery.append({"transition_offset": change["offset"], "recovery_seconds": pair - change["epoch"] if pair else None,
                             "definition": "two consecutive checksum-valid complete frames wholly within this regime",
                             "not_observed": pair is None})
        result["recovery"] = recovery
        write_json(folder / "result.json", result)
        print(f"{mode:9s} {scenario:7s} seed={seed}: packets={len(observed)} "
              + (f"failure={result['information_failure_rate']:.1%} goodput={result['verified_goodput_bps']:.1f} bit/s"
                 if mode != "benign" else "benign drift control"), flush=True)
        if recovered is not None:
            print(f"  Checksum-verified first message: {recovered!r}", flush=True)
        return result
    finally:
        halt.set()
        for process in (sender, receiver, capture):
            stop_process(process)


def evaluate(results, training):
    # Split whole runs: no neighboring windows straddle reference and threshold cohorts.
    detector = Detector(training[0]["capture_windows"],
                        calibration_windows=[window for item in training[1:] for window in item["capture_windows"]])
    for item in results:
        item["detections"] = [detector.predict(window) for window in item["capture_windows"]]
        item["alarm_metrics"] = {}
        for name in detector.thresholds:
            alarms = [w for w in item["detections"] if w["alarms"][name]]
            first = alarms[0]["epoch"] - item["start_epoch"] if alarms else None
            cutoff = alarms[0]["epoch"] if alarms else float("inf")
            delivered = sum(len(f["bits"]) for f in item["frame_results"] if f["verified"] and f["end_epoch"] < cutoff)
            item["alarm_metrics"][name] = {"positive_window_rate": len(alarms) / len(item["detections"]) if item["detections"] else None,
                                           "first_alarm_seconds": first, "alarm_observed": bool(alarms),
                                           "verified_bits_before_alarm": delivered if item["mode"] != "benign" else None}
    curves = {}
    for name in detector.thresholds:
        for mode in ("fixed", "naive", "corrected"):
            subset = [r for r in results if r["mode"] in (mode, "benign")]
            labels = [r["mode"] != "benign" for r in subset for _ in r["detections"]]
            scores = [w[name] for r in subset for w in r["detections"]]
            curves[f"{name}/{mode}"] = roc(labels, scores)
    return {"thresholds": detector.thresholds, "target_calibration_fpr": detector.target_fpr,
            "calibration_windows": detector.calibration_windows, "roc": curves,
            "calibration_run_ids": [r["id"] for r in training],
            "reference_run_ids": [training[0]["id"]], "threshold_run_ids": [r["id"] for r in training[1:]],
            "limitation": "ROC windows within runs are dependent; confidence intervals use independent run summaries."}


def suite(output, duration=8, repeats=3, scenarios=None, demo=False):
    if not (2 <= duration <= 120 and 1 <= repeats <= 20):
        raise ValueError("Duration must be 2-120 seconds and repeats 1-20")
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    scenarios = scenarios or ["clean", "abrupt", "gradual", "burst", "pacing"]
    training, results = [], []
    environment = {"kernel": platform.release(), "python": sys.version, "platform": platform.platform(),
                   "iproute2": run("tc", "-V"), "tcpdump": run("tcpdump", "--version"),
                   "duration_target": duration, "repeats": repeats, "scenarios": scenarios,
                   "topology": "10.77.0.1/24 -- virtual Ethernet -- 10.77.0.2/24",
                   "control_plane": "TCP/39002 unimpeded lab metadata/CRC/feedback; included in elapsed time",
                   "data_plane": "UDP/39001 12-byte constant-size frame/index metadata; message carried by gaps",
                   "created_epoch": time.time()}
    write_json(root / "environment.json", environment)
    with LabNetwork() as network:
        for seed in (1001, 1002, 1003):
            training.append(trial(network, root / f"calibration-clean-{seed}", "benign", "clean", seed, max(4, duration)))
        if demo:
            configurations = [("fixed", "clean"), ("fixed", "abrupt"), ("naive", "abrupt"),
                              ("corrected", "abrupt"), ("benign", "clean"), ("benign", "abrupt"), ("benign", "pacing")]
        else:
            configurations = [(mode, scenario) for scenario in scenarios for mode in ("fixed", "naive", "corrected", "benign")]
        for repeat in range(repeats):
            for mode, scenario in configurations:
                seed = 2001 + repeat
                result = trial(network, root / f"{scenario}-{mode}-{seed}", mode, scenario, seed, duration,
                               message="Kishen + Aarav | WhisperNet" if demo else "WhisperNet")
                results.append(result)
                write_json(root / "summary.partial.json", results)
    detection = evaluate(results, training)
    write_json(root / "summary.json", {"environment": environment, "calibration": training, "runs": results, "detection": detection})
    from .report import generate
    generate(root)
    return root
