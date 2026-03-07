"""Server resource monitoring during load tests.

Collects CPU, RAM, Disk I/O, and Network I/O metrics from Docker containers
by periodically sampling `docker stats` in a background thread.
"""
import asyncio
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContainerSample:
    """Single point-in-time sample of a container's resource usage."""
    timestamp: float
    container: str
    cpu_percent: float
    mem_usage_mb: float
    mem_limit_mb: float
    mem_percent: float
    net_rx_mb: float
    net_tx_mb: float
    block_read_mb: float
    block_write_mb: float


@dataclass
class ContainerStats:
    """Aggregated stats for a single container over the test duration."""
    container: str
    samples: int = 0
    cpu_avg: float = 0.0
    cpu_max: float = 0.0
    cpu_samples: list[float] = field(default_factory=list)
    mem_avg_mb: float = 0.0
    mem_max_mb: float = 0.0
    mem_limit_mb: float = 0.0
    mem_samples: list[float] = field(default_factory=list)
    net_rx_total_mb: float = 0.0
    net_tx_total_mb: float = 0.0
    block_read_total_mb: float = 0.0
    block_write_total_mb: float = 0.0

    def finalize(self):
        """Compute averages from collected samples."""
        if self.cpu_samples:
            self.cpu_avg = round(sum(self.cpu_samples) / len(self.cpu_samples), 2)
            self.cpu_max = round(max(self.cpu_samples), 2)
            self.samples = len(self.cpu_samples)
        if self.mem_samples:
            self.mem_avg_mb = round(sum(self.mem_samples) / len(self.mem_samples), 1)
            self.mem_max_mb = round(max(self.mem_samples), 1)

    def to_dict(self) -> dict:
        return {
            "container": self.container,
            "samples": self.samples,
            "cpu": {
                "avg_percent": self.cpu_avg,
                "max_percent": self.cpu_max,
            },
            "memory": {
                "avg_mb": self.mem_avg_mb,
                "max_mb": self.mem_max_mb,
                "limit_mb": self.mem_limit_mb,
                "max_usage_percent": round(
                    self.mem_max_mb / self.mem_limit_mb * 100, 1
                ) if self.mem_limit_mb > 0 else 0,
            },
            "network": {
                "rx_total_mb": round(self.net_rx_total_mb, 2),
                "tx_total_mb": round(self.net_tx_total_mb, 2),
            },
            "disk_io": {
                "read_total_mb": round(self.block_read_total_mb, 2),
                "write_total_mb": round(self.block_write_total_mb, 2),
            },
        }


def _parse_size(s: str) -> float:
    """Parse a Docker stats size string like '123.4MiB' to MB."""
    s = s.strip()
    if not s or s == "--":
        return 0.0
    match = re.match(r"([\d.]+)\s*(B|kB|KB|KiB|MB|MiB|GB|GiB|TB|TiB)", s)
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2)
    multipliers = {
        "B": 1 / (1024 * 1024),
        "kB": 1 / 1024, "KB": 1 / 1024, "KiB": 1 / 1024,
        "MB": 1, "MiB": 1,
        "GB": 1024, "GiB": 1024,
        "TB": 1024 * 1024, "TiB": 1024 * 1024,
    }
    return value * multipliers.get(unit, 1)


def _parse_io_pair(s: str) -> tuple[float, float]:
    """Parse 'X / Y' format from Docker stats (net I/O, block I/O)."""
    if not s or s == "--":
        return 0.0, 0.0
    parts = s.split("/")
    if len(parts) != 2:
        return 0.0, 0.0
    return _parse_size(parts[0]), _parse_size(parts[1])


# Docker stats --format with Go template produces consistent output
_DOCKER_FORMAT = (
    '{"container":"{{.Name}}",'
    '"cpu":"{{.CPUPerc}}",'
    '"mem_usage":"{{.MemUsage}}",'
    '"mem_perc":"{{.MemPerc}}",'
    '"net_io":"{{.NetIO}}",'
    '"block_io":"{{.BlockIO}}"}'
)

# Container name prefix filter for RFP Assistant
_CONTAINER_PREFIX = "rfp-assistant-"


class ServerMonitor:
    """Monitors Docker container resource usage during load tests.

    Runs `docker stats --no-stream` periodically in a background asyncio task
    and collects CPU, memory, network, and disk I/O samples.
    """

    def __init__(self, interval: float = 2.0, container_prefix: str = _CONTAINER_PREFIX):
        self.interval = interval
        self.container_prefix = container_prefix
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._samples: list[ContainerSample] = []
        self._stats: dict[str, ContainerStats] = {}
        self._docker_available: Optional[bool] = None

    def _check_docker(self) -> bool:
        """Check if docker CLI is available."""
        if self._docker_available is not None:
            return self._docker_available
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, timeout=5,
            )
            self._docker_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._docker_available = False
        return self._docker_available

    def _collect_sample(self) -> list[ContainerSample]:
        """Run docker stats --no-stream and parse results."""
        try:
            result = subprocess.run(
                [
                    "docker", "stats", "--no-stream",
                    "--format", _DOCKER_FORMAT,
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        samples = []
        now = time.time()
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            name = data.get("container", "")
            if not name.startswith(self.container_prefix):
                continue

            # Parse CPU%
            cpu_str = data.get("cpu", "0%").rstrip("%")
            try:
                cpu = float(cpu_str)
            except ValueError:
                cpu = 0.0

            # Parse memory usage / limit
            mem_parts = data.get("mem_usage", "0MiB / 0MiB").split("/")
            mem_usage = _parse_size(mem_parts[0]) if len(mem_parts) >= 1 else 0.0
            mem_limit = _parse_size(mem_parts[1]) if len(mem_parts) >= 2 else 0.0

            # Parse memory %
            mem_perc_str = data.get("mem_perc", "0%").rstrip("%")
            try:
                mem_perc = float(mem_perc_str)
            except ValueError:
                mem_perc = 0.0

            # Parse net I/O
            net_rx, net_tx = _parse_io_pair(data.get("net_io", "0B / 0B"))

            # Parse block I/O
            block_r, block_w = _parse_io_pair(data.get("block_io", "0B / 0B"))

            samples.append(ContainerSample(
                timestamp=now,
                container=name,
                cpu_percent=cpu,
                mem_usage_mb=mem_usage,
                mem_limit_mb=mem_limit,
                mem_percent=mem_perc,
                net_rx_mb=net_rx,
                net_tx_mb=net_tx,
                block_read_mb=block_r,
                block_write_mb=block_w,
            ))

        return samples

    async def _monitor_loop(self):
        """Background loop that samples docker stats periodically."""
        while self._running:
            # Run blocking docker call in thread pool
            loop = asyncio.get_event_loop()
            samples = await loop.run_in_executor(None, self._collect_sample)
            self._samples.extend(samples)
            await asyncio.sleep(self.interval)

    async def start(self):
        """Start background monitoring."""
        if not self._check_docker():
            print("  [Monitor] Docker CLI not available — server monitoring disabled")
            return False

        # Quick test: can we get stats?
        test_samples = self._collect_sample()
        if not test_samples:
            print("  [Monitor] No rfp-assistant containers found — server monitoring disabled")
            return False

        containers_found = set(s.container for s in test_samples)
        print(f"  [Monitor] Monitoring {len(containers_found)} container(s): "
              f"{', '.join(sorted(containers_found))}")

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        return True

    async def stop(self):
        """Stop monitoring and compute aggregates."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._aggregate()

    def _aggregate(self):
        """Compute per-container aggregates from raw samples."""
        by_container: dict[str, list[ContainerSample]] = {}
        for s in self._samples:
            by_container.setdefault(s.container, []).append(s)

        for name, samples in by_container.items():
            stats = ContainerStats(container=name)
            stats.cpu_samples = [s.cpu_percent for s in samples]
            stats.mem_samples = [s.mem_usage_mb for s in samples]
            stats.mem_limit_mb = samples[-1].mem_limit_mb if samples else 0

            # Network & disk: take the max seen (cumulative counters)
            stats.net_rx_total_mb = max(s.net_rx_mb for s in samples) if samples else 0
            stats.net_tx_total_mb = max(s.net_tx_mb for s in samples) if samples else 0
            stats.block_read_total_mb = max(s.block_read_mb for s in samples) if samples else 0
            stats.block_write_total_mb = max(s.block_write_mb for s in samples) if samples else 0

            stats.finalize()
            self._stats[name] = stats

    def get_report(self) -> dict:
        """Generate the server resources section of the report."""
        if not self._stats:
            return {}

        containers = {}
        for name, stats in sorted(self._stats.items()):
            short_name = name.replace(self.container_prefix, "")
            containers[short_name] = stats.to_dict()

        # Overall summary
        all_cpu = [s.cpu_avg for s in self._stats.values()]
        all_mem_max = [s.mem_max_mb for s in self._stats.values()]
        all_mem_limit = [s.mem_limit_mb for s in self._stats.values()]

        return {
            "overall": {
                "total_cpu_avg_percent": round(sum(all_cpu), 2),
                "total_mem_max_mb": round(sum(all_mem_max), 1),
                "total_mem_limit_mb": round(sum(all_mem_limit), 1),
                "total_mem_max_percent": round(
                    sum(all_mem_max) / sum(all_mem_limit) * 100, 1
                ) if sum(all_mem_limit) > 0 else 0,
            },
            "containers": containers,
        }

    def print_report(self):
        """Print a formatted server resource report."""
        report = self.get_report()
        if not report:
            print("\n  [Server Resources] No data collected (Docker not available or no containers found)")
            return report

        print("\n" + "=" * 72)
        print("  SERVER RESOURCES (Docker containers)")
        print("=" * 72)

        # Overall
        overall = report["overall"]
        print(f"\n  Total CPU (avg across all):  {overall['total_cpu_avg_percent']}%")
        print(f"  Total Memory (peak):         {overall['total_mem_max_mb']} MB / "
              f"{overall['total_mem_limit_mb']} MB "
              f"({overall['total_mem_max_percent']}%)")

        # Per container
        print(f"\n  {'Container':<28s} {'CPU avg':>8s} {'CPU max':>8s} "
              f"{'RAM avg':>9s} {'RAM max':>9s} {'RAM lim':>9s} "
              f"{'Net RX':>8s} {'Net TX':>8s} {'Disk R':>8s} {'Disk W':>8s}")
        print(f"  {'─' * 106}")

        for short_name, data in report["containers"].items():
            cpu = data["cpu"]
            mem = data["memory"]
            net = data["network"]
            disk = data["disk_io"]
            print(f"  {short_name:<28s} "
                  f"{cpu['avg_percent']:>7.1f}% {cpu['max_percent']:>7.1f}% "
                  f"{mem['avg_mb']:>7.0f}MB {mem['max_mb']:>7.0f}MB {mem['limit_mb']:>7.0f}MB "
                  f"{net['rx_total_mb']:>6.1f}MB {net['tx_total_mb']:>6.1f}MB "
                  f"{disk['read_total_mb']:>6.1f}MB {disk['write_total_mb']:>6.1f}MB")

        # Alerts
        print()
        alerts = []
        for short_name, data in report["containers"].items():
            if data["cpu"]["max_percent"] > 90:
                alerts.append(f"  [!] {short_name}: CPU peaked at {data['cpu']['max_percent']}%")
            if data["memory"]["max_usage_percent"] > 85:
                alerts.append(f"  [!] {short_name}: Memory peaked at "
                              f"{data['memory']['max_usage_percent']}% of limit")

        if alerts:
            print("  RESOURCE ALERTS:")
            for alert in alerts:
                print(alert)
        else:
            print("  No resource alerts — all containers within safe limits.")

        return report
