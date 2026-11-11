"""Submission capacities; per-task deadlines and reset checks stay independent."""

DEFAULT_TASKS_PER_WORKER = 32
MAX_TASKS_PER_WORKER = 32
MAX_PARALLEL_WORKERS = 6
# The native navigation probe accepts at most 7200 seconds per fresh cycle.
# 2700 startup seconds + (30 - 12) * 240 = 7020; 31 would exceed its cap.
MAX_NAVIGATION_CONTROL_TASKS = 30
LEGACY_SPECIAL_CONTROL_TASKS = 24
