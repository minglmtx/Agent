"""Distinguish a saved failure report from a completed model generation."""
import json
from pathlib import Path


def completed_generation(directory):
    for path in sorted(Path(directory).glob('generation-*.json')):
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (isinstance(row, dict) and row.get('status') == 'complete'
                and isinstance(row.get('response'), dict)
                and isinstance(row['response'].get('text'), str)
                and row['response']['text'].strip()):
            return str(path)
    return None
