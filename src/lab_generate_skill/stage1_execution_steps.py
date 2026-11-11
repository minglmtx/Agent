"""Selection counter from an admitted runtime, never inferred from model prose.

The counter increments after session.step returns, including a returned tool error
or finish call. It excludes reset, failed parses and terminal observations. It is
not a count of successful actions or a replacement for native/runtime evidence.
"""
METRIC = "recorded_environment_step_returns_v1"

def require_metric(value):
    if value.get("selection_metric") != METRIC:
        raise ValueError("Legacy or unknown selection metric: use its frozen runtime; no automatic cache migration")

def selection_steps(trace):
    p = trace.get("provenance", {})
    count, rounds = p.get("environment_steps"), trace.get("rounds")
    if (trace.get("error") is not None or trace.get("sample_status", "completed") != "completed"
            or p.get("execution_step_metric") != METRIC
            or type(count) is not int or type(rounds) is not int
            or not 0 <= count <= rounds):
        raise ValueError("Explicit complete environment-step counter required; generation rounds are not a fallback")
    return count
