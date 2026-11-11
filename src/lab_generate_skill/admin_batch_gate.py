"""A complete runtime check, not an actor success threshold, gates the next job."""
import json
from pathlib import Path
from .admin_batch import classify_attempts


def check_previous(base, index):
    if index==0:return
    previous=Path(base)/'extension'/f'online-shard-{index-1:02d}'
    complete=previous/'complete.json'
    if not complete.exists() or not json.loads(complete.read_text()).get('complete'):
        raise ValueError('Previous runtime job did not complete; stop the batch')
    summary=json.loads((previous/'summary.json').read_text())
    if len(summary['tasks'])!=1:raise ValueError('Expected one previous task')
    status=classify_attempts(summary['tasks'][0]['results'])
    if status not in ('all_failed','has_success'):
        raise ValueError('Previous task had incomplete, invalid or runtime-error conditions: '+status)
