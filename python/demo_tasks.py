"""Six tiny coding tasks. Evaluator/reference code stays outside agent workdirs.

This is evaluation separation, NOT a same-user filesystem security boundary.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ORDERS = '''import csv
from decimal import Decimal

def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def total(rows):
    return sum((Decimal(r["price"]) * int(r["quantity"]) for r in rows), Decimal("0")).quantize(Decimal("0.01"))
'''
CLI = '''import argparse
from orders import load, total

p = argparse.ArgumentParser()
p.add_argument("input")
a = p.parse_args()
rows = load(a.input)
print(total(rows))
'''
TASKS = [
    {"id": "quantity", "split": "dev", "family": "bugfix", "prompt": "Fix total: each row contributes unit price times integer quantity. Keep exact two-decimal output."},
    {"id": "empty", "split": "test", "family": "bugfix", "prompt": "Fix header-only CSV input: it must print 0.00 and exit successfully. Preserve normal totals."},
    {"id": "status", "split": "dev", "family": "feature", "prompt": "Add optional --status VALUE, filtering rows by exact status before calculating total. With no flag preserve existing behavior; no matches prints 0.00."},
    {"id": "json", "split": "test", "family": "feature", "prompt": 'Add --format with choices text (default) and json. JSON output must be {"count": <row count>, "total": "<two-decimal string>"}. Preserve default text output.'},
    {"id": "discount", "split": "dev", "family": "multi-file", "prompt": "Add --discount-percent (default 0, decimal 0 through 100). Implement total(rows, discount_percent='0') in orders.py and call it from CLI. Apply discount to the subtotal then round to cents using ROUND_HALF_UP. Reject percentages outside 0..100 with a nonzero exit."},
    {"id": "input", "split": "test", "family": "multi-file", "prompt": "Support --input-file PATH as an alternative to the existing positional input. Exactly one source is required; reject both/neither. Update orders.load to accept UTF-8 CSV with or without a BOM, preserving original positional use."},
]
CSV = "id,price,quantity,status\nA,0.10,3,paid\nB,2.35,2,pending\n"


def sources(task_id, solved=False):
    orders, cli = ORDERS, CLI
    if task_id == "quantity" and not solved:
        orders = orders.replace(' * int(r["quantity"])', "")
    if task_id == "empty" and not solved:
        orders = orders.replace('    return sum(', '    rows[0]["price"]\n    return sum(')
    if solved and task_id == "status":
        cli = cli.replace("a = p.parse_args()", 'p.add_argument("--status")\na = p.parse_args()')
        cli = cli.replace("print(total(rows))", 'rows = [r for r in rows if a.status is None or r["status"] == a.status]\nprint(total(rows))')
    if solved and task_id == "json":
        cli = "import json\n" + cli.replace("a = p.parse_args()", 'p.add_argument("--format", choices=["text", "json"], default="text")\na = p.parse_args()')
        cli = cli.replace("print(total(rows))", 'print(json.dumps({"count": len(rows), "total": str(total(rows))}) if a.format == "json" else total(rows))')
    if solved and task_id == "discount":
        orders = orders.replace("import Decimal", "import Decimal, ROUND_HALF_UP").replace("def total(rows):", "def total(rows, discount_percent='0'):\n    discount = Decimal(discount_percent)\n    if not 0 <= discount <= 100:\n        raise ValueError('discount must be within 0..100')")
        orders = orders.replace('return sum(', 'return (sum(').replace('Decimal("0")).quantize(Decimal("0.01"))', 'Decimal("0")) * (1 - discount / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)')
        cli = cli.replace("a = p.parse_args()", 'p.add_argument("--discount-percent", default="0")\na = p.parse_args()').replace("total(rows)", "total(rows, a.discount_percent)")
    if solved and task_id == "input":
        orders = orders.replace('"utf-8"', '"utf-8-sig"')
        cli = cli.replace('p.add_argument("input")', 'p.add_argument("input", nargs="?")\np.add_argument("--input-file")')
        cli = cli.replace("rows = load(a.input)", 'if bool(a.input) == bool(a.input_file):\n    p.error("provide exactly one input")\nrows = load(a.input or a.input_file)')
    return {"orders.py": orders, "cli.py": cli}


def create_fixture(task_id, workdir, solved=False):
    workdir.mkdir(parents=True, exist_ok=False)
    for name, content in sources(task_id, solved).items():
        (workdir / name).write_text(content)
    (workdir / "sample.csv").write_text(CSV)


def evaluate(task_id, workdir):
    """Run external assertions against CLI; no model or gold files in workdir."""
    checks = []
    with tempfile.TemporaryDirectory(prefix="coding-agent-acceptance-") as tmp:
        root = Path(tmp)
        (root / "data.csv").write_text(CSV)
        (root / "empty.csv").write_text(CSV.splitlines()[0] + "\n")
        (root / "bom.csv").write_text("\ufeff" + CSV)
        def check(name, args, expected=None, nonzero=False, as_json=False, code=None):
            try:
                command = [sys.executable, "-B", *(["-c", code] if code else [str(workdir / "cli.py")]), *map(str, args)]
                result = subprocess.run(command,
                                        cwd=workdir, capture_output=True, text=True, timeout=5)
                value = json.loads(result.stdout) if as_json and result.returncode == 0 else result.stdout.strip()
                passed = result.returncode != 0 if nonzero else result.returncode == 0 and value == expected
                checks.append({"name": name, "passed": passed, "returncode": result.returncode,
                               "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]})
            except (subprocess.TimeoutExpired, ValueError) as exc:
                checks.append({"name": name, "passed": False, "error": str(exc)})
        data, empty = root / "data.csv", root / "empty.csv"
        check("existing_total", [data], "5.00")
        check("empty_input", [empty], "0.00")
        if task_id == "status":
            for status, value in [("paid", "0.30"), ("pending", "4.70"), ("missing", "0.00")]:
                check(status, [data, "--status", status], value)
        if task_id == "json":
            check("json_total", [data, "--format", "json"], {"count": 2, "total": "5.00"}, as_json=True)
            check("json_empty", [empty, "--format", "json"], {"count": 0, "total": "0.00"}, as_json=True)
            check("invalid_format", [data, "--format", "xml"], nonzero=True)
        if task_id == "discount":
            check("module_discount_api", [data], "2.50", code="import orders,sys; print(orders.total(orders.load(sys.argv[1]), '50'))")
            for pct, expected in [("10", "4.50"), ("100", "0.00"), ("99.9", "0.01")]:
                check("discount_" + pct, [data, "--discount-percent", pct], expected)
            check("invalid_discount", [data, "--discount-percent", "101"], nonzero=True)
            check("negative_discount", [data, "--discount-percent", "-1"], nonzero=True)
        if task_id == "input":
            check("module_bom_api", [root / "bom.csv"], "A", code="import orders,sys; print(orders.load(sys.argv[1])[0]['id'])")
            check("named_bom", ["--input-file", root / "bom.csv"], "5.00")
            check("positional_bom", [root / "bom.csv"], "5.00")
            check("both_sources", [data, "--input-file", data], nonzero=True)
            check("neither_source", [], nonzero=True)
    return {"passed": all(c["passed"] for c in checks), "checks": checks}
