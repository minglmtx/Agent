"""Check the actual frozen runner's direct native-runtime API before compute."""
import ast
import hashlib
from pathlib import Path


def require_interfaces(runner, *, aliases=('native_read_runtime','native_csv_runtime')):
    path = Path(runner.__file__)
    source = path.read_bytes()
    tree = ast.parse(source)
    calls = {alias:set() for alias in aliases}
    for node in ast.walk(tree):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                and isinstance(node.func.value,ast.Name) and node.func.value.id in calls):
            calls[node.func.value.id].add(node.func.attr)
    missing = []
    for alias, names in calls.items():
        module = getattr(runner,alias,None)
        for name in sorted(names):
            if not callable(getattr(module,name,None)):
                missing.append(alias+'.'+name)
    if missing:
        raise ValueError('Frozen runner runtime interface missing: '+', '.join(missing))
    return dict(passed=True, runner_sha256=hashlib.sha256(source).hexdigest(),
                interfaces={k:sorted(v) for k,v in calls.items()},
                native_sites_started=0, model_calls=0, api_calls=0)
