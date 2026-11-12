#!/usr/bin/env python3
"""Bounded HTTP load test for a running JARVIS server.

The script sends only the request path you specify, makes no provider calls, and
refuses non-loopback targets unless --allow-remote is set. It is intended for
comparing local process and container performance on the same machine.

Exit codes:
    0  completed and the error rate stayed within --max-error-rate
    1  completed but the error rate exceeded --max-error-rate
    2  invalid arguments or target
    130 interrupted
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass
class Result:
    label: str
    url: str
    concurrency: int
    duration_s: float
    elapsed_s: float
    requests: int
    errors: int
    error_rate: float
    rps: float
    mean_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    statuses: dict[str, int]
    error_kinds: dict[str, int]


def percentile(ordered: list[float], fraction: float) -> float:
    """Nearest-rank percentile over an ascending sample list."""
    if not ordered:
        return 0.0
    index = round(fraction * (len(ordered) - 1))
    return ordered[min(len(ordered) - 1, max(0, index))]


async def worker(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    timeout: float,
    deadline: float,
    latencies: list[float],
    statuses: Counter[int],
    errors: Counter[str],
) -> None:
    while time.perf_counter() < deadline:
        started = time.perf_counter()
        try:
            response = await client.get(url, headers=headers, timeout=timeout)
            statuses[response.status_code] += 1
        except Exception as exc:  # noqa: BLE001 - every transport failure is a data point
            errors[type(exc).__name__] += 1
        latencies.append(time.perf_counter() - started)


async def run(args: argparse.Namespace) -> Result:
    parsed = httpx.URL(args.url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("--url must use http:// or https://")
    if parsed.host not in LOOPBACK_HOSTS and not args.allow_remote:
        raise ValueError("refusing a non-loopback target without --allow-remote")
    if args.concurrency < 1 or args.duration <= 0 or args.warmup < 0:
        raise ValueError("concurrency must be >= 1, duration > 0, warmup >= 0")

    token = args.token or os.environ.get(args.token_env, "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    limits = httpx.Limits(
        max_connections=args.concurrency,
        max_keepalive_connections=args.concurrency,
    )
    latencies: list[float] = []
    statuses: Counter[int] = Counter()
    errors: Counter[str] = Counter()

    async with httpx.AsyncClient(
        trust_env=False,
        limits=limits,
        timeout=args.timeout,
        follow_redirects=False,
    ) as client:
        for _ in range(args.warmup):
            try:
                await client.get(args.url, headers=headers, timeout=args.timeout)
            except Exception:  # noqa: BLE001 - warmup failures are not scored
                pass

        started = time.perf_counter()
        deadline = started + args.duration
        await asyncio.gather(
            *(
                worker(
                    client,
                    args.url,
                    headers,
                    args.timeout,
                    deadline,
                    latencies,
                    statuses,
                    errors,
                )
                for _ in range(args.concurrency)
            )
        )
        elapsed = time.perf_counter() - started

    ordered = sorted(latencies)
    total_errors = sum(errors.values())
    requests = len(ordered)
    error_rate = (total_errors / requests) if requests else 0.0
    return Result(
        label=args.label,
        url=args.url,
        concurrency=args.concurrency,
        duration_s=args.duration,
        elapsed_s=round(elapsed, 3),
        requests=requests,
        errors=total_errors,
        error_rate=round(error_rate, 6),
        rps=round(requests / elapsed, 2) if elapsed > 0 else 0.0,
        mean_ms=round(statistics.fmean(ordered) * 1000, 2) if ordered else 0.0,
        p50_ms=round(percentile(ordered, 0.50) * 1000, 2),
        p90_ms=round(percentile(ordered, 0.90) * 1000, 2),
        p95_ms=round(percentile(ordered, 0.95) * 1000, 2),
        p99_ms=round(percentile(ordered, 0.99) * 1000, 2),
        max_ms=round(ordered[-1] * 1000, 2) if ordered else 0.0,
        statuses={str(code): count for code, count in sorted(statuses.items())},
        error_kinds=dict(errors),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="Full URL, loopback by default")
    parser.add_argument("--label", default="run", help="Label printed with the result")
    parser.add_argument("--duration", type=float, default=10.0, help="Measured seconds (default: 10)")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers (default: 10)")
    parser.add_argument("--warmup", type=int, default=5, help="Sequential warmup requests (default: 5)")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout seconds")
    parser.add_argument("--token", default="", help="Bearer token; prefer --token-env")
    parser.add_argument(
        "--token-env",
        default="JARVIS_API_TOKEN",
        help="Environment variable holding the bearer token (default: JARVIS_API_TOKEN)",
    )
    parser.add_argument("--max-error-rate", type=float, default=0.01, help="Fail above this rate")
    parser.add_argument("--json-out", type=Path, help="Write the summary as JSON to this path")
    parser.add_argument("--allow-remote", action="store_true", help="Permit non-loopback targets")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except ValueError as exc:
        print(f"load_test: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("load_test: interrupted", file=sys.stderr)
        return 130

    print(json.dumps(asdict(result), indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    if result.error_rate > args.max_error_rate:
        print(
            f"load_test: error rate {result.error_rate:.4f} exceeds {args.max_error_rate:.4f}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
