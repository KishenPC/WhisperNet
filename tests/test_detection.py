import struct

import numpy as np
import pytest

from whispernet.core import DATA_PORT
from whispernet.detection import Detector, pcap_times, roc, windows


def test_pcap_parser_filters_ports_and_preserves_arrival_times(tmp_path):
    header = struct.pack("<IHHIIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
    records = []
    for microseconds, port in ((1000, DATA_PORT), (2000, 1234), (3000, DATA_PORT)):
        ethernet = b"\x00" * 12 + b"\x08\x00"
        ip = bytearray(20)
        ip[0], ip[9] = 0x45, 17
        udp = struct.pack("!HHHH", 45000, port, 8, 0)
        packet = ethernet + ip + udp
        records.append(struct.pack("<IIII", 10, microseconds, len(packet), len(packet)) + packet)
    path = tmp_path / "trace.pcap"
    path.write_bytes(header + b"".join(records))
    assert pcap_times(path).tolist() == pytest.approx([10.001, 10.003])


def test_corrupt_pcap_is_rejected(tmp_path):
    path = tmp_path / "bad.pcap"
    path.write_bytes(b"junk")
    with pytest.raises(ValueError):
        pcap_times(path)


def test_windows_do_not_overlap():
    result = windows(np.arange(11) * .01, size=4)
    assert len(result) == 2
    assert result[0]["epoch"] == pytest.approx(.04)
    assert result[1]["epoch"] == pytest.approx(.08)


def test_normalized_score_is_invariant_to_uniform_time_scaling():
    rng = np.random.default_rng(22)
    training = [{"gaps": rng.lognormal(-3.8, .30, 32).tolist()} for _ in range(20)]
    model = Detector(training)
    trace = rng.lognormal(-3.8, .30, 32)
    assert model.score(trace)["normalized_temporal"] == pytest.approx(model.score(trace * 4)["normalized_temporal"])
    assert model.score(trace * 4)["raw_ks"] > model.score(trace)["raw_ks"]


def test_evaluation_does_not_mutate_calibration():
    rng = np.random.default_rng(22)
    model = Detector([{"gaps": rng.lognormal(-3.8, .30, 32).tolist()} for _ in range(20)])
    thresholds = model.thresholds.copy()
    reference = model.reference.copy()
    model.predict({"epoch": 1, "gaps": [10.0] * 32})
    assert model.thresholds == thresholds
    assert np.array_equal(model.reference, reference)


def test_explicit_reference_and_threshold_cohorts_stay_separate():
    rng = np.random.default_rng(43)
    reference = [{"gaps": rng.lognormal(-3.8, .30, 32).tolist()} for _ in range(4)]
    calibration = [{"gaps": rng.lognormal(-3.8, .30, 32).tolist()} for _ in range(8)]
    model = Detector(reference, calibration_windows=calibration)
    assert model.calibration_windows == 8
    assert np.array_equal(model.reference, np.concatenate([w["gaps"] for w in reference]))
    for name, threshold in model.thresholds.items():
        expected = np.quantile([model.score(w["gaps"])[name] for w in calibration], .95, method="higher")
        assert threshold == pytest.approx(expected)


def test_roc_handles_ties_and_perfect_ranking():
    assert roc([0, 0, 1, 1], [0, 0, 1, 1])["auc"] == pytest.approx(1)
    assert roc([0, 1], [1, 1])["auc"] == pytest.approx(.5)
    assert roc([0, 0], [1, 2])["auc"] is None

