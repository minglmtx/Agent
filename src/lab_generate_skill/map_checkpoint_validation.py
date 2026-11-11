"""Candidate-only native HTTP validation of a completed, immutable Map checkpoint.

This never publishes/replaces the normal baseline or imports geographic rows.
"""
import hashlib,json,time
from pathlib import Path
import xml.etree.ElementTree as ET
from .map_query_site import IsolatedMapQuerySite
from .pg_checkpoint_restore import restore_checkpoint
from .map_current_tables import PROJECTIONS
from .io_utils import atomic_write_json as save


def completed_checkpoint(path,digest):
    path=Path(path);raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Checkpoint receipt changed')
    data=json.loads(raw)
    if (data.get('version')!='map28-native-pg11-closed-checkpoint-v2'
        or any(data.get(k)is not True for k in ('all_current_tables_complete','table_projections_complete','native_finalization_complete'))
        or set(data.get('verified_current_tables',{}))!=set(PROJECTIONS)
        or any(row.get('whole_row_projection_equal')is not True for row in data['verified_current_tables'].values())
        or len(data.get('archives',[]))!=1 or data['archives'][0]['file']!='base.tar'):
        raise ValueError('All eight exact current tables and native finalization required')
    return data


class CheckpointValidationSite(IsolatedMapQuerySite):
    """Use one restored copy for all native read/reset probes; no default switch."""
    def __init__(self,root,logs,*,checkpoint,checkpoint_sha256,restore_seconds=4500):
        self.checkpoint=Path(checkpoint);self.checkpoint_sha256=checkpoint_sha256
        self.checkpoint_record=completed_checkpoint(checkpoint,checkpoint_sha256)
        self.restore_seconds=restore_seconds
        super().__init__(root,logs,with_geographic_baseline=True,track_changes=True)

    def load_geographic_baseline(self,images):
        completed_checkpoint(self.checkpoint,self.checkpoint_sha256)
        return dict(version='unpublished-map-checkpoint-validation-v1',checkpoint_sha256=self.checkpoint_sha256,
            native_HTTP_validation_complete=False,training_admissions=0,
            archive_sha256=self.checkpoint_record['archives'][0]['sha256'])

    def prepare_app_database(self,state,db):
        start=time.monotonic()
        receipt=restore_checkpoint(self.checkpoint,state/'pg',budget_seconds=self.restore_seconds,
            progress=lambda count,seconds:save(self.logs/'checkpoint-restore-progress.json',dict(bytes=count,seconds=seconds,complete=False)))
        if receipt['recovery_still_required']:raise ValueError('Expected closed database, not a recovery experiment')
        save(self.logs/'checkpoint-restore.json',receipt)
        save(self.logs/'checkpoint-restore-progress.json',dict(bytes=self.checkpoint_record['archives'][0]['bytes'],seconds=time.monotonic()-start,complete=True))
        self.event('verified_checkpoint_restore',start,source_modified=False,import_repeated=False)


def object_matches(kind,reference,body):
    if kind not in ('node','way','relation'):raise ValueError('Native OSM object kind required')
    tree=ET.fromstring(body)
    if tree.tag!='osm':return False
    objects=tree.findall(kind)
    if len(objects)!=1:return False
    node=objects[0]
    if node.get('id')!=str(reference['id'])or node.get('version')!=str(reference['version']):return False
    if node.get('visible')not in (None,'true'):return False
    if kind=='node':
        try:
            if abs(float(node.get('lat'))-reference['latitude']/1e7)>1e-7 or abs(float(node.get('lon'))-reference['longitude']/1e7)>1e-7:return False
        except (TypeError,ValueError):return False
    actual=sorted((n.get('k'),n.get('v'))for n in node.findall('tag'))
    return actual==sorted(tuple(x)for x in reference['tags'])
