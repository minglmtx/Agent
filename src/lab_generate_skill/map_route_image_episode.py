"""Original-start route image collection with terminal-only artifact scoring."""
from copy import deepcopy
import json
from pathlib import Path
from .map_candidate_start import InitialStartHooks
from .map_route_image_request import native_line
from .map_route_image_downloads import evaluate
from .map_raster_observation import render_reference
from .io_utils import atomic_write_json


class RouteImageHooks(InitialStartHooks):
    def __init__(self,candidate,directory,*,baseline,references):
        if candidate.get('candidate_completion',{}).get('family')!='route_png_artifact':
            raise ValueError('Explicit route image task required')
        for ref in references:native_line(ref)
        super().__init__(deepcopy(candidate),None)
        self.directory=Path(directory);self.baseline=baseline;self.references=deepcopy(references)
        self.closed=self.scored=False;self.receipt_path=None

    def prepare(self,site,username):
        if self.site is not None or username is not None or not all(getattr(site,k,False)for k in ('with_tiles','with_geographic_baseline','track_changes','native_share_observer','raster_installed')):
            raise ValueError('One isolated tracked native raster site required')
        site.reset_guard.require_unchanged()
        if site.fingerprint()!=self.baseline:raise ValueError('Route image initial baseline changed')
        self.site=site;self.receipt_path=site.state/'tiles/raster-receipts.jsonl'
        if self.receipt_path.is_symlink():raise ValueError('Renderer receipt stream is not owned')
        stat=self.receipt_path.stat() if self.receipt_path.exists() else None
        self.receipt_inode=stat.st_ino if stat else None;self.receipt_offset=stat.st_size if stat else 0
        self.events.append('prepare')

    def observe_initial(self,page):
        super().observe_initial(page)
        atomic_write_json(self.directory/'route-image-initial.json',self.initial)

    def close(self):
        if not self.closed:super().close();self.closed=True

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or not self.closed or self.terminal is None or terminal!=self.terminal:
            raise ValueError('One bound completed image episode required')
        self.scored=True;integrity=False;receipts=None
        try:
            site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.baseline
            if self.receipt_path.is_symlink():raise ValueError('Renderer receipt stream redirected')
            stat=self.receipt_path.stat() if self.receipt_path.exists() else None
            if (stat is None and self.receipt_inode is not None) or (stat is not None and
                ((self.receipt_inode is not None and stat.st_ino!=self.receipt_inode) or
                 not 0<=stat.st_size-self.receipt_offset<=16*1024*1024)):
                raise ValueError('Owned receipt stream changed')
            raw=b''
            if stat is not None:
                with self.receipt_path.open('rb')as f:f.seek(self.receipt_offset);raw=f.read()
            if raw and not raw.endswith(b'\n'):raise ValueError('Incomplete renderer receipt')
            receipts=[json.loads(line)for line in raw.splitlines()]
        except (OSError,ValueError,RuntimeError):integrity=False
        judgment=evaluate(self.directory/'browser-downloads',self.references,receipts,
            render_reference=lambda request:render_reference(site,request),
            evidence_directory=self.directory/'independent-renders',integrity=integrity,runtime_error=runtime_error)
        self.events.append('score_terminal')
        atomic_write_json(self.directory/'route-image-terminal.json',dict(events=self.events,
            terminal=terminal,integrity=integrity,receipts=receipts,receipt_offset=self.receipt_offset,
            private_renders_excluded_from_actor_receipts=True,judgment=judgment))
        return judgment,integrity
