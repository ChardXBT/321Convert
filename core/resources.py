"""Memory-aware resource limits for conversion workers.

``memory_limit`` reads the container's cgroup memory ceiling so concurrency
can be clamped to what the instance actually has; ``limit_memory`` adds a
bounded writable-memory budget inside each conversion child to reject
oversized allocations before they exhaust the instance.
"""

import sys
from pathlib import Path

from core import config


def memory_limit() -> int | None:
    """Read the cgroup namespace root used in Docker/Render; v1 fallback."""
    limits = []
    for path in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        try:
            value = int(path.read_text().strip())
        except (OSError, ValueError):
            continue
        if 0 < value < 1 << 60:
            limits.append(value)
    return min(limits) if limits else None


def concurrency_limit() -> int:
    requested = max(1, config.MAX_CONCURRENT_CONVERSIONS)
    limit = memory_limit()
    # Reserve 192 MiB for web server, forkserver, uploads and responses.
    if limit is not None:
        available = max(0, limit - 192 * config.MIB)
        return min(requested, max(1, available // max(1, config.CONVERSION_MEMORY_BYTES)))
    return requested


def limit_memory() -> None:
    """Cap growth of Linux writable private data; shared mappings and file
    cache are accounted separately by the cgroup. The limit reduces memory
    exhaustion risk but is not a complete bound on resident memory.

    RLIMIT_DATA also covers private writable mappings on Linux >= 4.7.
    Unlike RLIMIT_AS, it permits read-only library mappings without granting
    the same headroom to private buffers.
    """
    if sys.platform != "linux" or config.CONVERSION_MEMORY_BYTES <= 0:
        return
    import resource

    data_bytes = 0
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmData:"):
            data_bytes = int(line.split()[1]) * 1024
            break
    ceiling = data_bytes + config.CONVERSION_MEMORY_BYTES
    soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
    if soft != resource.RLIM_INFINITY:
        ceiling = min(ceiling, soft)
    if hard != resource.RLIM_INFINITY:
        ceiling = min(ceiling, hard)
    resource.setrlimit(resource.RLIMIT_DATA, (ceiling, hard))
