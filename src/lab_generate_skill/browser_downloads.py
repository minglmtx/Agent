"""Native browser download feedback, independent of task goals and evaluators.

Enabled by the shared recorded runners after two-instance runtime validation.
The original action error is retained: an attachment can finish even when the
same click reports a navigation timeout. No retry or completion reward is added.
"""
import hashlib
from pathlib import Path

from .io_utils import atomic_write_json
from .runtime_watchdog import deadline_scope


class DownloadRecorder:
    def __init__(self, context, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.pending = []
        self.records = []
        self.pages = set()
        self.context = context
        context.on('page', self.attach)
        for page in context.pages:
            self.attach(page)

    def attach(self, page):
        if page not in self.pages:
            self.pages.add(page)
            page.on('download', lambda item: self.pending.append(item))

    def collect(self):
        # Only a real download event permits waiting. The enclosing rollout
        # watchdog remains authoritative and can be shorter than this bound.
        while self.pending:
            item = self.pending.pop(0)
            ident = len(self.records) + 1
            row = {'download_id': ident, 'filename': str(item.suggested_filename)[:256],
                   'status': 'pending'}
            self.records.append(row)
            self.save()
            with deadline_scope('browser_download_artifact', 120):
                failure = item.failure()
                if failure is not None:
                    # Do not expose arbitrary backend URLs or filesystem paths.
                    row['status'] = 'failed'
                else:
                    output = self.directory / ('artifact-%04d.bin' % ident)
                    item.save_as(output)
                    digest = hashlib.sha256()
                    with output.open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(chunk)
                    row.update(status='completed', bytes=output.stat().st_size,
                               sha256=digest.hexdigest())
            self.save()
        return [dict(row) for row in self.records]

    def save(self):
        atomic_write_json(self.directory / 'downloads.json', {'downloads': self.records,
                          'task_success_inferred': False, 'extra_browser_actions': 0})


def add_download_observation(observation, records):
    if not records:
        return observation
    return {**observation, 'downloads': records,
            'download_feedback': 'Native browser download status. A completed attachment does not '
            'by itself establish that the task goal was met. Action errors are recorded separately.'}
