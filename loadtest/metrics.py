"""Metrics collection and reporting for load tests."""
import time
import statistics
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional


@dataclass
class RequestMetric:
    """Single HTTP request metric."""
    user_id: int
    step: str
    method: str
    url: str
    status_code: int
    duration_ms: float
    success: bool
    error: Optional[str] = None
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class AIOperationMetric:
    """Tracks the real wall-clock duration of an AI operation (dispatch → completion).

    This measures the TOTAL time from when the async task is dispatched until polling
    confirms it completed — giving the true AI processing time including queue wait,
    LLM inference, and any retries.
    """
    user_id: int
    operation: str  # generate_structure, generate_content, compliance_analysis, etc.
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_s: float = 0.0
    poll_count: int = 0
    final_status: str = ""  # completed, failed, timeout
    success: bool = False

    def finish(self, status: str, poll_count: int = 0):
        self.finished_at = time.monotonic()
        self.duration_s = round(self.finished_at - self.started_at, 2)
        self.final_status = status
        self.poll_count = poll_count
        self.success = status in ("completed", "ready", "idle")


@dataclass
class UserJourneyMetric:
    """Full user journey metric."""
    user_id: int
    started_at: float = 0.0
    finished_at: float = 0.0
    steps_completed: int = 0
    steps_total: int = 0
    success: bool = False
    error: Optional[str] = None


class MetricsCollector:
    """Thread-safe metrics collector."""

    def __init__(self):
        self.requests: list[RequestMetric] = []
        self.journeys: list[UserJourneyMetric] = []
        self.ai_operations: list[AIOperationMetric] = []
        self._server_resources: dict = {}
        self._start_time: float = 0.0
        self._end_time: float = 0.0

    def start(self):
        self._start_time = time.time()

    def stop(self):
        self._end_time = time.time()

    def record_request(self, metric: RequestMetric):
        self.requests.append(metric)

    def record_journey(self, journey: UserJourneyMetric):
        self.journeys.append(journey)

    def record_ai_operation(self, op: AIOperationMetric):
        self.ai_operations.append(op)

    def set_server_resources(self, resources: dict):
        self._server_resources = resources

    @property
    def total_duration_s(self) -> float:
        return self._end_time - self._start_time

    def generate_report(self) -> dict:
        """Generate a comprehensive report."""
        if not self.requests:
            return {"error": "No requests recorded"}

        total_requests = len(self.requests)
        successful = [r for r in self.requests if r.success]
        failed = [r for r in self.requests if not r.success]
        durations = [r.duration_ms for r in self.requests]
        success_durations = [r.duration_ms for r in successful]

        # Per-step breakdown
        by_step = defaultdict(list)
        for r in self.requests:
            by_step[r.step].append(r)

        step_stats = {}
        for step_name, reqs in by_step.items():
            durs = [r.duration_ms for r in reqs]
            ok = sum(1 for r in reqs if r.success)
            step_stats[step_name] = {
                "count": len(reqs),
                "success": ok,
                "failed": len(reqs) - ok,
                "success_rate": round(ok / len(reqs) * 100, 1),
                "avg_ms": round(statistics.mean(durs), 1),
                "median_ms": round(statistics.median(durs), 1),
                "p95_ms": round(_percentile(durs, 95), 1),
                "p99_ms": round(_percentile(durs, 99), 1),
                "min_ms": round(min(durs), 1),
                "max_ms": round(max(durs), 1),
            }

        # Per-status-code breakdown
        by_status = defaultdict(int)
        for r in self.requests:
            by_status[r.status_code] += 1

        # Journey stats
        journey_successes = sum(1 for j in self.journeys if j.success)
        journey_durations = [
            (j.finished_at - j.started_at) * 1000
            for j in self.journeys
            if j.finished_at > 0
        ]

        # Throughput
        rps = total_requests / self.total_duration_s if self.total_duration_s > 0 else 0

        # Error details
        errors = []
        for r in failed:
            errors.append({
                "user": r.user_id,
                "step": r.step,
                "method": r.method,
                "url": _truncate_url(r.url),
                "status": r.status_code,
                "error": r.error or "",
            })

        # AI operation timing (real wall-clock durations)
        ai_ops_stats = {}
        if self.ai_operations:
            by_op = defaultdict(list)
            for op in self.ai_operations:
                by_op[op.operation].append(op)

            for op_name, ops in by_op.items():
                durations_s = [op.duration_s for op in ops if op.duration_s > 0]
                ok = sum(1 for op in ops if op.success)
                polls = [op.poll_count for op in ops]
                ai_ops_stats[op_name] = {
                    "count": len(ops),
                    "success": ok,
                    "failed": len(ops) - ok,
                    "avg_duration_s": round(statistics.mean(durations_s), 2) if durations_s else 0,
                    "min_duration_s": round(min(durations_s), 2) if durations_s else 0,
                    "max_duration_s": round(max(durations_s), 2) if durations_s else 0,
                    "p95_duration_s": round(_percentile(durations_s, 95), 2) if durations_s else 0,
                    "avg_poll_count": round(statistics.mean(polls), 1) if polls else 0,
                    "statuses": dict(defaultdict(int, {
                        op.final_status: sum(1 for o in ops if o.final_status == op.final_status)
                        for op in ops
                    })),
                }

        report = {
            "summary": {
                "total_duration_s": round(self.total_duration_s, 2),
                "total_requests": total_requests,
                "successful_requests": len(successful),
                "failed_requests": len(failed),
                "success_rate": round(len(successful) / total_requests * 100, 1),
                "requests_per_second": round(rps, 2),
            },
            "latency": {
                "avg_ms": round(statistics.mean(durations), 1),
                "median_ms": round(statistics.median(durations), 1),
                "p95_ms": round(_percentile(durations, 95), 1),
                "p99_ms": round(_percentile(durations, 99), 1),
                "min_ms": round(min(durations), 1),
                "max_ms": round(max(durations), 1),
            },
            "ai_operations": ai_ops_stats,
            "journeys": {
                "total": len(self.journeys),
                "successful": journey_successes,
                "failed": len(self.journeys) - journey_successes,
                "avg_duration_ms": round(statistics.mean(journey_durations), 1) if journey_durations else 0,
            },
            "status_codes": dict(sorted(by_status.items())),
            "steps": step_stats,
            "errors": errors[:50],  # cap at 50
        }

        # Attach server resource data if available
        if self._server_resources:
            report["server_resources"] = self._server_resources

        return report

    def print_report(self):
        """Print a formatted report to stdout."""
        report = self.generate_report()
        if "error" in report:
            print(f"\n  No data: {report['error']}")
            return report

        s = report["summary"]
        lat = report["latency"]
        j = report["journeys"]

        print("\n" + "=" * 72)
        print("  LOAD TEST REPORT")
        print("=" * 72)

        # Summary
        print(f"\n  Duration:           {s['total_duration_s']}s")
        print(f"  Total requests:     {s['total_requests']}")
        print(f"  Successful:         {s['successful_requests']}")
        print(f"  Failed:             {s['failed_requests']}")
        print(f"  Success rate:       {s['success_rate']}%")
        print(f"  Throughput:         {s['requests_per_second']} req/s")

        # Latency
        print(f"\n  {'Latency':20s} {'Avg':>10s} {'Median':>10s} {'P95':>10s} {'P99':>10s} {'Max':>10s}")
        print(f"  {'─' * 70}")
        print(f"  {'Overall':20s} {lat['avg_ms']:>9.1f}ms {lat['median_ms']:>9.1f}ms "
              f"{lat['p95_ms']:>9.1f}ms {lat['p99_ms']:>9.1f}ms {lat['max_ms']:>9.1f}ms")

        # Per-step
        print(f"\n  {'Step':30s} {'Count':>6s} {'OK%':>6s} {'Avg':>10s} {'P95':>10s} {'Max':>10s}")
        print(f"  {'─' * 72}")
        for step_name, stats in report["steps"].items():
            print(f"  {step_name:30s} {stats['count']:>6d} {stats['success_rate']:>5.1f}% "
                  f"{stats['avg_ms']:>9.1f}ms {stats['p95_ms']:>9.1f}ms {stats['max_ms']:>9.1f}ms")

        # AI Operations (real wall-clock durations)
        ai_ops = report.get("ai_operations", {})
        if ai_ops:
            print(f"\n  {'AI Operation':30s} {'Count':>6s} {'OK%':>6s} {'Avg':>8s} "
                  f"{'P95':>8s} {'Max':>8s} {'Polls':>7s}")
            print(f"  {'─' * 76}")
            for op_name, stats in ai_ops.items():
                ok_pct = round(stats['success'] / stats['count'] * 100, 1) if stats['count'] > 0 else 0
                print(f"  {op_name:30s} {stats['count']:>6d} {ok_pct:>5.1f}% "
                      f"{stats['avg_duration_s']:>6.1f}s "
                      f"{stats['p95_duration_s']:>6.1f}s "
                      f"{stats['max_duration_s']:>6.1f}s "
                      f"{stats['avg_poll_count']:>5.0f}x")

        # Journeys
        print(f"\n  User Journeys:      {j['total']} total, {j['successful']} OK, {j['failed']} failed")
        if j['avg_duration_ms']:
            print(f"  Avg journey time:   {j['avg_duration_ms']:.0f}ms")

        # Status codes
        print(f"\n  HTTP Status Codes:")
        for code, count in report["status_codes"].items():
            print(f"    {code}: {count}")

        # Errors (first 10)
        if report["errors"]:
            print(f"\n  Errors (showing first 10):")
            for e in report["errors"][:10]:
                print(f"    [User {e['user']}] {e['step']}: {e['method']} {e['url']} -> {e['status']} {e['error'][:80]}")

        # Verdict
        print("\n" + "=" * 72)
        verdict = self.verdict(report)
        print(f"  VERDICT: {verdict['status']}")
        print(f"  {verdict['message']}")
        print("=" * 72 + "\n")

        return report

    def verdict(self, report: dict = None) -> dict:
        """Return pass/fail verdict based on thresholds."""
        if report is None:
            report = self.generate_report()

        if "error" in report or "summary" not in report:
            return {
                "status": "FAIL",
                "message": report.get("error", "No data collected — is the server running?"),
                "pass": False,
            }

        s = report["summary"]
        lat = report["latency"]
        j = report["journeys"]

        issues = []

        # Success rate must be >= 95%
        if s["success_rate"] < 95:
            issues.append(f"Success rate {s['success_rate']}% < 95%")

        # P95 latency should be < 30s (generous for AI calls)
        if lat["p95_ms"] > 30000:
            issues.append(f"P95 latency {lat['p95_ms']}ms > 30s")

        # All journeys should complete
        if j["total"] > 0 and j["failed"] > j["total"] * 0.2:
            issues.append(f"{j['failed']}/{j['total']} journeys failed (> 20%)")

        # AI operations: check for failures and extreme latency
        ai_ops = report.get("ai_operations", {})
        for op_name, stats in ai_ops.items():
            if stats["count"] > 0:
                fail_rate = stats["failed"] / stats["count"]
                if fail_rate > 0.3:
                    issues.append(f"AI '{op_name}': {stats['failed']}/{stats['count']} failed (> 30%)")
                if stats["p95_duration_s"] > 180:
                    issues.append(f"AI '{op_name}': P95 = {stats['p95_duration_s']}s (> 180s)")

        # No 5xx errors tolerated beyond 5%
        total_5xx = sum(
            count for code, count in report["status_codes"].items()
            if 500 <= code < 600
        )
        if total_5xx > s["total_requests"] * 0.05:
            issues.append(f"{total_5xx} server errors (> 5% of requests)")

        if issues:
            return {
                "status": "FAIL",
                "message": "Issues found: " + "; ".join(issues),
                "pass": False,
            }

        return {
            "status": "PASS",
            "message": f"All checks passed. {s['total_requests']} requests, "
                       f"{s['success_rate']}% success rate, "
                       f"P95={lat['p95_ms']}ms, {j['successful']}/{j['total']} journeys OK.",
            "pass": True,
        }


def _percentile(data: list[float], p: float) -> float:
    """Calculate percentile."""
    if not data:
        return 0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return d0 + d1


def _truncate_url(url: str, max_len: int = 60) -> str:
    if len(url) <= max_len:
        return url
    return url[:max_len - 3] + "..."
