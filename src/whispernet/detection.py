"""Offline payload-independent detection from captured UDP packet times."""

import math
from pathlib import Path
import struct

import numpy as np
from scipy.stats import ks_2samp

from .core import DATA_PORT


def pcap_times(path):
    formats = {b"\xd4\xc3\xb2\xa1": ("<", 1e6), b"\xa1\xb2\xc3\xd4": (">", 1e6),
               b"\x4d\x3c\xb2\xa1": ("<", 1e9), b"\xa1\xb2\x3c\x4d": (">", 1e9)}
    times = []
    with Path(path).open("rb") as stream:
        header = stream.read(24)
        if len(header) != 24 or header[:4] not in formats:
            raise ValueError("Expected a classic PCAP capture")
        endian, scale = formats[header[:4]]
        if struct.unpack(endian + "I", header[20:24])[0] != 1:
            raise ValueError("Expected Ethernet capture; use the lab eth0 capture")
        while packet_header := stream.read(16):
            if len(packet_header) != 16:
                raise ValueError("Truncated PCAP record")
            seconds, fraction, captured, _ = struct.unpack(endian + "IIII", packet_header)
            if captured > 65536:
                raise ValueError("Unexpected PCAP record size")
            packet = stream.read(captured)
            if len(packet) != captured:
                raise ValueError("Truncated PCAP packet")
            if len(packet) < 42 or packet[12:14] != b"\x08\x00":
                continue
            ihl = (packet[14] & 15) * 4
            start = 14 + ihl
            if ihl < 20 or packet[23] != 17 or len(packet) < start + 8:
                continue
            _, destination = struct.unpack("!HH", packet[start:start + 4])
            if destination == DATA_PORT:
                times.append(seconds + fraction / scale)
    return np.array(times)


def windows(times, size=32):
    gaps = np.diff(times)
    if np.any(gaps < 0):
        raise ValueError("Capture timestamps are not ordered")
    return [{"epoch": float(times[i + size]), "gaps": gaps[i:i + size].tolist()}
            for i in range(0, len(gaps) - size + 1, size)]


def entropy(values):
    bins = np.array([0, .003, .006, .012, .024, .048, .096, .192, 1, np.inf])
    counts, _ = np.histogram(values, bins=bins)
    p = counts[counts > 0] / max(1, counts.sum())
    return float(-np.sum(p * np.log2(p)))


def correlation(values):
    if len(values) < 4 or np.std(values[:-1]) < 1e-12 or np.std(values[1:]) < 1e-12:
        return 0.0
    return float(np.corrcoef(values[:-1], values[1:])[0, 1])


class Detector:
    """Clean-run calibration; evaluation traces never update its references or thresholds."""

    def __init__(self, training_windows, target_fpr=.05, calibration_windows=None):
        if calibration_windows is None and len(training_windows) < 8:
            raise ValueError("At least eight benign calibration windows are needed")
        values = [np.array(window["gaps"]) for window in training_windows]
        if calibration_windows is None:
            split = max(2, len(values) // 2)
            reference, calibration = values[:split], values[split:]
        else:
            reference = values
            calibration = [np.array(window["gaps"]) for window in calibration_windows]
            if len(reference) < 4 or len(calibration) < 4:
                raise ValueError("Separate reference and threshold cohorts each need at least four windows")
        self.reference = np.concatenate(reference)
        self.normalized_reference = np.concatenate([x / max(np.median(x), 1e-6) for x in reference])
        self.reference_entropy = float(np.mean([entropy(x) for x in reference]))
        self.reference_correlation = float(np.mean([correlation(x) for x in reference]))
        scored = [self.score(x) for x in calibration]
        self.thresholds = {name: float(np.quantile([x[name] for x in scored], 1 - target_fpr, method="higher"))
                           for name in ("ks_entropy", "normalized_temporal")}
        self.target_fpr = target_fpr
        self.calibration_windows = len(calibration)

    def score(self, values):
        values = np.asarray(values)
        raw_ks = float(ks_2samp(values, self.reference).statistic)
        relative = values / max(np.median(values), 1e-6)
        normalized_ks = float(ks_2samp(relative, self.normalized_reference).statistic)
        return {"ks_entropy": raw_ks + abs(entropy(values) - self.reference_entropy) / 4,
                "normalized_temporal": normalized_ks + abs(correlation(values) - self.reference_correlation) / 2,
                "raw_ks": raw_ks, "entropy": entropy(values), "lag1_correlation": correlation(values)}

    def predict(self, window):
        scores = self.score(window["gaps"])
        return {"epoch": window["epoch"], **scores,
                "alarms": {name: scores[name] > threshold for name, threshold in self.thresholds.items()}}


def roc(labels, scores):
    labels, scores = np.asarray(labels, dtype=bool), np.asarray(scores, dtype=float)
    if not labels.any() or labels.all():
        return {"fpr": [], "tpr": [], "auc": None}
    thresholds = np.r_[np.inf, np.sort(np.unique(scores))[::-1], -np.inf]
    points = [(float(np.mean(scores[~labels] >= t)), float(np.mean(scores[labels] >= t))) for t in thresholds]
    fpr, tpr = map(np.array, zip(*points))
    return {"fpr": fpr.tolist(), "tpr": tpr.tolist(), "auc": float(np.trapezoid(tpr, fpr) if hasattr(np, "trapezoid") else np.trapz(tpr, fpr))}
