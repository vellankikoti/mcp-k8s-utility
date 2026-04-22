from __future__ import annotations

from utility_server.tools.right_size_workload.analyze import parse_cpu, parse_memory_mib


def test_parse_cpu_millicores():
    assert parse_cpu("500m") == 0.5
    assert parse_cpu("125m") == 0.125


def test_parse_cpu_bare_number():
    assert parse_cpu("2") == 2.0
    assert parse_cpu(1.5) == 1.5


def test_parse_cpu_nano_micro():
    assert parse_cpu("1000000000n") == 1.0
    assert parse_cpu("1000000u") == 1.0


def test_parse_cpu_none_or_bad():
    assert parse_cpu(None) == 0.0
    assert parse_cpu("garbage") == 0.0


def test_parse_memory_binary_units():
    assert parse_memory_mib("256Mi") == 256.0
    assert parse_memory_mib("1Gi") == 1024.0
    assert parse_memory_mib("2048Ki") == 2.0


def test_parse_memory_decimal_units_approx():
    # 1M = 1_000_000 bytes ≈ 0.9537 MiB
    out = parse_memory_mib("1M")
    assert 0.95 < out < 0.96


def test_parse_memory_none_or_bad():
    assert parse_memory_mib(None) == 0.0
    assert parse_memory_mib("gibberish") == 0.0
