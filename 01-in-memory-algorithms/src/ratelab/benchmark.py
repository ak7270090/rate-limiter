"""Measure every algorithm: memory per key, burst behaviour, boundary straddle, throughput.

``python -m ratelab.benchmark`` writes ``results/algorithm-comparison.md``.
"""

import argparse
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path

from ratelab.algorithm_registry import IN_MEMORY_LIMITERS, create_in_memory_limiter
from ratelab.clock import FakeClock
from ratelab.rate_limiter import RateLimitRule

COMPARISON_FILE_NAME = "algorithm-comparison.md"
BENCHMARK_RULE = RateLimitRule(limit=100, window_seconds=10.0)
BOUNDARY_SECONDS = 1_000_000.0


@dataclass(frozen=True)
class BenchmarkSettings:
    key_counts: tuple[int, ...] = (1, 10_000, 100_000)
    operation_count: int = 200_000
    memory_key_count: int = 10_000
    results_dir: Path = Path("results")


@dataclass(frozen=True)
class AlgorithmMeasurement:
    algorithm: str
    bytes_per_full_key: float
    admitted_from_idle_burst: int
    admitted_around_reset: int
    operations_per_second: dict[int, float]


def admitted_in_burst(algorithm: str, clock: FakeClock, request_count: int, key: str) -> int:
    limiter = create_in_memory_limiter(algorithm, BENCHMARK_RULE, clock)
    return sum(limiter.try_acquire(key).is_allowed for _ in range(request_count))


def measure_admitted_around_reset(algorithm: str) -> int:
    """Burst ``limit`` 0.5 s before a fixed-window reset and ``limit`` 0.2 s after it."""
    clock = FakeClock(BOUNDARY_SECONDS - 0.5)
    limiter = create_in_memory_limiter(algorithm, BENCHMARK_RULE, clock)
    admitted = sum(limiter.try_acquire("k").is_allowed for _ in range(BENCHMARK_RULE.limit))
    clock.set(BOUNDARY_SECONDS + 0.2)
    admitted += sum(limiter.try_acquire("k").is_allowed for _ in range(BENCHMARK_RULE.limit))
    return admitted


def measure_bytes_per_full_key(algorithm: str, key_count: int) -> float:
    """Memory per key after each key has used its whole limit at one instant."""
    clock = FakeClock(BOUNDARY_SECONDS)
    limiter = create_in_memory_limiter(algorithm, BENCHMARK_RULE, clock)
    keys = [f"key-{index}" for index in range(key_count)]
    tracemalloc.start()
    before, _ = tracemalloc.get_traced_memory()
    for key in keys:
        for _ in range(BENCHMARK_RULE.limit):
            limiter.try_acquire(key)
    after, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return (after - before) / key_count


def measure_operations_per_second(algorithm: str, key_count: int, operation_count: int) -> float:
    clock = FakeClock(BOUNDARY_SECONDS)
    limiter = create_in_memory_limiter(algorithm, BENCHMARK_RULE, clock)
    keys = [f"key-{index}" for index in range(key_count)]
    started = time.perf_counter()
    for operation_index in range(operation_count):
        clock.advance(0.0001)
        limiter.try_acquire(keys[operation_index % key_count])
    return operation_count / (time.perf_counter() - started)


def measure_algorithm(algorithm: str, settings: BenchmarkSettings) -> AlgorithmMeasurement:
    return AlgorithmMeasurement(
        algorithm=algorithm,
        bytes_per_full_key=measure_bytes_per_full_key(algorithm, settings.memory_key_count),
        admitted_from_idle_burst=admitted_in_burst(
            algorithm, FakeClock(BOUNDARY_SECONDS), 2 * BENCHMARK_RULE.limit, "k"
        ),
        admitted_around_reset=measure_admitted_around_reset(algorithm),
        operations_per_second={
            key_count: measure_operations_per_second(algorithm, key_count, settings.operation_count)
            for key_count in settings.key_counts
        },
    )


def render_comparison(measurements: list[AlgorithmMeasurement], settings: BenchmarkSettings) -> str:
    rule = BENCHMARK_RULE
    throughput_headers = " | ".join(f"ops/s at {count:,} key(s)" for count in settings.key_counts)
    lines = [
        f"# Algorithm comparison: {rule.limit} requests / {rule.window_seconds:g} s",
        "",
        "Measured in one Python process with a fake clock, single run, so throughput is noisy "
        f"({settings.operation_count:,} operations per throughput run, "
        f"memory over {settings.memory_key_count:,} keys).",
        "",
        f"| Algorithm | Bytes per key (full window) | Admitted from {2 * rule.limit} at once "
        f"| Admitted: {rule.limit} before + {rule.limit} after a reset | {throughput_headers} |",
        "|---|---|---|---|" + "---|" * len(settings.key_counts),
    ]
    for measurement in measurements:
        throughput = " | ".join(
            f"{measurement.operations_per_second[count]:,.0f}" for count in settings.key_counts
        )
        lines.append(
            f"| {measurement.algorithm} | {measurement.bytes_per_full_key:,.0f} "
            f"| {measurement.admitted_from_idle_burst} | {measurement.admitted_around_reset} "
            f"| {throughput} |"
        )
    return "\n".join(lines) + "\n"


def run_benchmark(settings: BenchmarkSettings) -> Path:
    measurements = [measure_algorithm(name, settings) for name in IN_MEMORY_LIMITERS]
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    output_path = settings.results_dir / COMPARISON_FILE_NAME
    output_path.write_text(render_comparison(measurements, settings), encoding="utf-8")
    return output_path


def parse_settings(arguments: list[str] | None = None) -> BenchmarkSettings:
    defaults = BenchmarkSettings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-counts", type=int, nargs="+", default=list(defaults.key_counts))
    parser.add_argument("--operations", type=int, default=defaults.operation_count)
    parser.add_argument("--memory-keys", type=int, default=defaults.memory_key_count)
    parser.add_argument("--results-dir", type=Path, default=defaults.results_dir)
    parsed = parser.parse_args(arguments)
    return BenchmarkSettings(
        key_counts=tuple(parsed.key_counts),
        operation_count=parsed.operations,
        memory_key_count=parsed.memory_keys,
        results_dir=parsed.results_dir,
    )


def main(arguments: list[str] | None = None) -> None:
    output_path = run_benchmark(parse_settings(arguments))
    print(output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
