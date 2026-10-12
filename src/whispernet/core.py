"""Timing symbols, synchronization, estimators and receiver decoding."""

from dataclasses import dataclass
import math
import statistics
import struct
import zlib

DATA_PORT = 39001
CONTROL_PORT = 39002
PACKET = struct.Struct("!4sII")
MAGIC = b"WN01"
PILOT = [0, 1, 0, 1, 1, 0, 1, 0]
MODES = ("fixed", "naive", "corrected", "benign")


def to_bits(data: bytes) -> list[int]:
    return [(value >> shift) & 1 for value in data for shift in range(7, -1, -1)]


def to_bytes(bits: list[int]) -> bytes:
    if len(bits) % 8 or any(bit not in (0, 1) for bit in bits):
        raise ValueError("Byte reconstruction needs complete groups of eight binary bits")
    return bytes(sum(bits[i + j] << (7 - j) for j in range(8)) for i in range(0, len(bits), 8))


def checksum(data: bytes) -> int:
    return zlib.crc32(data)


@dataclass(frozen=True)
class Timing:
    short: float = 0.012
    long: float = 0.036

    def __post_init__(self):
        if not (math.isfinite(self.short) and math.isfinite(self.long)
                and 0.001 <= self.short < self.long <= 0.5):
            raise ValueError("Timing gaps must be finite, ordered and between 1 and 500 ms")

    @property
    def threshold(self):
        return (self.short + self.long) / 2

    def gap(self, bit):
        return self.long if bit else self.short


def choose_timing(mode: str, feedback: dict | None, current: Timing) -> Timing:
    if mode not in MODES:
        raise ValueError(f"Unknown controller: {mode}")
    if mode in ("fixed", "benign") or not feedback or feedback.get("pilot_samples", 0) < 4:
        return current
    sigma = feedback["raw_sigma" if mode == "naive" else "residual_sigma"]
    if not math.isfinite(sigma) or sigma < 0:
        return current
    separation = min(0.160, max(0.016, 4 * sigma))
    return Timing(0.012, 0.012 + separation)


def decode_frame(meta: dict, arrivals: list[dict]) -> dict:
    timing = Timing(meta["short"], meta["long"])
    count = meta["payload_bits"]
    if not (0 < count <= 512 and count % 8 == 0):
        raise ValueError("Invalid frame length")
    total = len(PILOT) + count
    decoded: list[int | None] = [None] * total
    seen = set()
    raw, residual = [], []
    previous = None
    reorder = duplicates = 0
    for event in arrivals:
        index = event["index"]
        if index in seen:
            duplicates += 1
            continue
        if not 0 <= index <= total:
            continue
        seen.add(index)
        if previous is not None:
            gap = (event["timestamp_ns"] - previous["timestamp_ns"]) / 1e9
            if index <= previous["index"]:
                reorder += 1
            # A missing packet merges intervals. Never classify the merged gap as one symbol.
            elif index == previous["index"] + 1 and gap >= 0:
                decoded[index - 1] = int(gap > timing.threshold)
                if index <= len(PILOT):
                    raw.append(gap)
                    residual.append(gap - timing.gap(PILOT[index - 1]))
        previous = event
    payload = decoded[len(PILOT):]
    complete = all(bit is not None for bit in payload)
    data = to_bytes(payload) if complete else None
    return {
        "frame": meta["frame"], "bits": payload,
        "verified": complete and checksum(data) == meta["crc32"],
        "text": data.decode("utf-8", errors="replace") if complete else None,
        "data_hex": data.hex() if complete else None,
        "erasures": payload.count(None), "reordered": reorder, "duplicates": duplicates,
        "packets_expected": total + 1, "packets_received": len(seen),
        "packet_loss_fraction": (total + 1 - len(seen)) / (total + 1),
        "pilot_samples": len(raw),
        "raw_sigma": statistics.pstdev(raw) if len(raw) >= 2 else 0.0,
        "residual_sigma": statistics.pstdev(residual) if len(residual) >= 2 else 0.0,
        "short": timing.short, "long": timing.long,
    }


def metrics(expected: list[list[int]], frames: list[dict], elapsed: float) -> dict:
    total = sum(map(len, expected))
    substitutions = erasures = verified_bits = delivered_frames = 0
    for truth, frame in zip(expected, frames):
        observed = frame["bits"]
        if len(truth) != len(observed):
            raise ValueError("Frame alignment mismatch")
        erasures += sum(bit is None for bit in observed)
        substitutions += sum(bit is not None and bit != wanted for bit, wanted in zip(observed, truth))
        # Both the checksum and original bits are checked by the offline evaluator.
        if frame["verified"] and observed == truth:
            delivered_frames += 1
            verified_bits += len(truth)
    if len(frames) != len(expected):
        raise ValueError("Missing frame results must be recorded as failures, not dropped")
    received = sum(f["packets_received"] for f in frames)
    sent = sum(f["packets_expected"] for f in frames)
    return {
        "information_bits": total, "substitutions": substitutions, "erasures": erasures,
        "substitution_rate": substitutions / total if total else 0,
        "erasure_rate": erasures / total if total else 0,
        "information_failure_rate": (substitutions + erasures) / total if total else 0,
        "conditional_ber": substitutions / (total - erasures) if total > erasures else None,
        "verified_information_bits": verified_bits,
        "verified_goodput_bps": verified_bits / elapsed,
        "raw_information_rate_bps": total / elapsed,
        "frame_success_rate": delivered_frames / len(expected) if expected else 0,
        "frames": len(expected), "elapsed_seconds": elapsed,
        "observed_packet_loss": (sent - received) / sent if sent else 0,
        "reordered_packets": sum(f["reordered"] for f in frames),
    }

