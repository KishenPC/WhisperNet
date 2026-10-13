from types import SimpleNamespace

import pytest

from whispernet import network


def test_waits_for_first_time_update_before_accepting_capture(monkeypatch):
    replies = iter([SimpleNamespace(returncode=0),
                    SimpleNamespace(returncode=0, stdout="Packet count: 0"),
                    SimpleNamespace(returncode=0, stdout="Packet count: 1")])
    sleeps = []
    monkeypatch.setattr(network.shutil, "which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr(network.subprocess, "run", lambda *a, **k: next(replies))
    monkeypatch.setattr(network.time, "sleep", sleeps.append)
    assert network.await_clock_sync() == {"checked": True, "ntp_packets": 1}
    assert sleeps == [1]


def test_unsynchronized_clock_times_out_instead_of_starting_capture(monkeypatch):
    replies = iter([SimpleNamespace(returncode=0), SimpleNamespace(returncode=0, stdout="Packet count: 0")])
    clock = iter([0, 2])
    monkeypatch.setattr(network.shutil, "which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr(network.subprocess, "run", lambda *a, **k: next(replies))
    monkeypatch.setattr(network.time, "monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError, match="clock has not synchronized"):
        network.await_clock_sync(timeout=1)


def test_inactive_time_service_does_not_require_ntp(monkeypatch):
    monkeypatch.setattr(network.shutil, "which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr(network.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=3))
    assert network.await_clock_sync() == {"checked": False, "reason": "systemd-timesyncd inactive"}


def test_wsl_time_service_is_restored_when_experiment_fails(monkeypatch):
    commands=[]
    monkeypatch.setattr(network.platform, "release", lambda: "6.18-microsoft-standard-WSL2")
    monkeypatch.setattr(network.shutil, "which", lambda _: "/usr/bin/systemctl")
    monkeypatch.setattr(network.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(network, "run", lambda *a: commands.append(a))
    with pytest.raises(RuntimeError, match="trial failed"):
        with network.measurement_clock() as status:
            assert status["guest_time_service_paused"]
            raise RuntimeError("trial failed")
    assert commands == [("systemctl", "stop", "systemd-timesyncd"),
                        ("systemctl", "start", "systemd-timesyncd")]


def test_native_linux_uses_clock_readiness_without_pausing_services(monkeypatch):
    monkeypatch.setattr(network.platform, "release", lambda: "6.18-generic")
    monkeypatch.setattr(network, "await_clock_sync", lambda: {"checked": True, "ntp_packets": 2})
    with network.measurement_clock() as status:
        assert status == {"checked": True, "ntp_packets": 2}
