import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("resource_probe", Path(__file__).with_name("resource_probe.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize("host", ["8.8.8.8", "169.254.1.2", "0.0.0.0", "example.com", "192.168.1.1/path"])
def test_public_or_invalid_target_refused(host):
    with pytest.raises(ValueError):
        probe.exercise(host)


def test_bounds_and_summary(monkeypatch):
    seen = []
    monkeypatch.setattr(probe, "sample", lambda url: (seen.append(url) is None, .01, 100))
    monkeypatch.setattr(probe, "memory_sample", lambda: {"available_kib": 700, "swap_used_kib": 10})
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)
    report = probe.exercise("192.168.1.4", rounds=2, kiwix=True)
    assert len(seen) == 6
    assert report["targets"]["portal_health"] == {"requests": 2, "successful": 2, "bytes": 200, "p95_ms": 10.0}
    assert report["probe_machine_memory"]["min_available_kib"] == 700
    for kwargs in ({"rounds": 101}, {"concurrency": 9}, {"port": 0}):
        with pytest.raises(ValueError):
            probe.exercise("192.168.1.4", **kwargs)


def test_memory_sample(tmp_path):
    path = tmp_path / "meminfo"
    path.write_text("MemTotal: 1000 kB\nMemAvailable: 700 kB\nSwapTotal: 500 kB\nSwapFree: 450 kB\n")
    assert probe.memory_sample(path) == {"total_kib": 1000, "available_kib": 700, "swap_used_kib": 50}
    assert probe.memory_sample(tmp_path / "missing") is None


def test_failed_requests_are_counted():
    assert probe.summarize([(False, .2, 0), (True, .1, 10)]) == {
        "requests": 2, "successful": 1, "bytes": 10, "p95_ms": 200.0}
