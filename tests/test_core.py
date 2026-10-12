import math

import pytest

from whispernet.core import PILOT, Timing, checksum, choose_timing, decode_frame, metrics, to_bits, to_bytes


def frame(data=b"Hi", removed=(), ordering=None, noise=None):
    timing = Timing()
    bits = PILOT + to_bits(data)
    meta = {"frame": 0, "payload_bits": len(data) * 8, "crc32": checksum(data), "short": timing.short, "long": timing.long}
    timestamps = [0]
    for i, bit in enumerate(bits):
        timestamps.append(timestamps[-1] + int((timing.gap(bit) + (noise[i] if noise else 0)) * 1e9))
    events = [{"index": i, "timestamp_ns": t} for i, t in enumerate(timestamps) if i not in removed]
    if ordering:
        events = [events[i] for i in ordering]
    return meta, events


def test_all_byte_values_round_trip():
    data = bytes(range(256))
    assert to_bytes(to_bits(data)) == data


def test_reject_invalid_reconstruction_and_timing():
    with pytest.raises(ValueError):
        to_bytes([0, 1])
    with pytest.raises(ValueError):
        Timing(float("nan"), .030)
    with pytest.raises(ValueError):
        Timing(.040, .020)


def test_clean_frame_is_recovered_and_verified():
    meta, events = frame()
    decoded = decode_frame(meta, events)
    assert decoded["bits"] == to_bits(b"Hi")
    assert decoded["verified"]
    assert decoded["text"] == "Hi"
    assert decoded["erasures"] == 0
    assert decoded["residual_sigma"] < 1e-8


def test_lost_packet_does_not_turn_merged_interval_into_a_bit():
    meta, events = frame(removed=(10,))
    decoded = decode_frame(meta, events)
    assert decoded["bits"][1:3] == [None, None]
    assert decoded["erasures"] == 2
    assert not decoded["verified"]
    assert decoded["packets_expected"] - decoded["packets_received"] == 1


def test_lost_anchor_erases_first_pilot_only():
    meta, events = frame(removed=(0,))
    decoded = decode_frame(meta, events)
    assert decoded["pilot_samples"] == 7
    assert decoded["verified"]


def test_reordering_marks_unobservable_symbols_as_erasures():
    meta, events = frame()
    events[10], events[11] = events[11], events[10]
    decoded = decode_frame(meta, events)
    assert decoded["reordered"] == 1
    assert not decoded["verified"]
    assert decoded["erasures"] >= 2


def test_duplicates_do_not_change_valid_decoding():
    meta, events = frame()
    events.insert(11, events[10])
    decoded = decode_frame(meta, events)
    assert decoded["verified"]
    assert decoded["duplicates"] == 1


def test_wrong_checksum_fails_even_with_complete_bits():
    meta, events = frame()
    meta["crc32"] ^= 1
    decoded = decode_frame(meta, events)
    assert decoded["erasures"] == 0
    assert not decoded["verified"]


def test_estimators_separate_symbol_variation_from_noise():
    meta, events = frame()
    feedback = decode_frame(meta, events)
    assert feedback["raw_sigma"] == pytest.approx(.012)
    assert feedback["residual_sigma"] == pytest.approx(0, abs=1e-8)
    naive = choose_timing("naive", feedback, Timing())
    corrected = choose_timing("corrected", feedback, Timing())
    assert naive.long - naive.short > corrected.long - corrected.short


def test_controller_is_bounded_and_holds_when_pilots_are_missing():
    feedback = {"pilot_samples": 8, "raw_sigma": 100, "residual_sigma": 100}
    assert choose_timing("corrected", feedback, Timing()).long == pytest.approx(.172)
    feedback["pilot_samples"] = 2
    assert choose_timing("corrected", feedback, Timing()) == Timing()


def test_metric_accounting_keeps_lost_information_in_denominator():
    meta, events = frame(removed=(10,))
    result = metrics([to_bits(b"Hi")], [decode_frame(meta, events)], 2)
    assert result["erasure_rate"] == 2 / 16
    assert result["verified_goodput_bps"] == 0
    assert result["information_bits"] == 16


def test_missing_frame_cannot_silently_disappear():
    with pytest.raises(ValueError):
        metrics([to_bits(b"Hi")], [], 2)

