"""An explicit, job-bound stop channel independent of Slurm RPC delivery."""
import json
from pathlib import Path
import time

VERSION='map-checkpoint-stop-request-v1'


class CheckpointStopRequested(InterruptedError):
    pass


class CheckpointStopRequest:
    def __init__(self,path,*,job_id,checkpoint_sha256,event,interval_seconds=2):
        self.path=Path(path);self.job_id=str(job_id);self.checkpoint_sha256=checkpoint_sha256
        self.event=event;self.interval_seconds=interval_seconds;self.last_poll=None;self.accepted=None;self.rejected=None

    def poll(self,phase):
        now=time.monotonic()
        if self.accepted is None and (self.last_poll is None or now-self.last_poll>=self.interval_seconds):
            self.last_poll=now
            if self.path.exists():
                if self.path.is_symlink() or not self.path.is_file():
                    self.rejected='Checkpoint stop request must be a regular file'
                    return False
                try:value=json.loads(self.path.read_text())
                except (OSError,ValueError):
                    self.rejected='Unreadable or incomplete stop request'
                    return False
                if (not isinstance(value,dict) or set(value)!={'version','job_id','checkpoint_sha256','action'}
                        or value['version']!=VERSION or value['job_id']!=self.job_id
                        or value['checkpoint_sha256']!=self.checkpoint_sha256
                        or value['action']!='preserve_and_stop'):
                    self.rejected='Stop request does not match this job and source checkpoint'
                    return False
                self.accepted=value
                self.rejected=None
                self.event.set()
        if self.accepted is not None and phase=='restoring_and_hashing_in_one_read':
            # No new database computation exists yet. Interrupt the private
            # restore copy; the durable source archive is never modified.
            raise CheckpointStopRequested('Explicit stop requested during restore; source checkpoint retained')
        # During database work, existing transaction/range boundaries observe
        # the event and preserve committed state. Never interrupt checkpoint
        # archive writing or cleanup in response to a second stop request.
        return self.accepted is not None
