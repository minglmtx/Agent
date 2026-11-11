"""Exact dedicated editor fixture, installed before the native reset baseline."""
from copy import deepcopy
from pathlib import Path
import hashlib
from editor_site import EditorSite
from edit_protection import INSTALL

EXPECTED = {'version': 'native-saved-node-editor-profile-v190', 'source_task_id': '35984f23d32598fe54dd', 'account': {'email': 'local-map-editor@example.test', 'display_name': 'Local Test Map Editor', 'password': 'LocalMapEditor-2026!'}, 'presets': {'path': '/home/atuin/r102bf/r102bf10/lmtx/datasets/map-editor-assets/id-tagging-schema-6.0.0', 'manifest': {'path': '/home/atuin/r102bf/r102bf10/lmtx/datasets/map-editor-assets/id-tagging-schema-6.0.0/manifest.json', 'sha256': '3b5539733d91376c7d3bcb343b5218e70450d84ad87e092895cae24497556f05'}}}

def validate_profile(value):
 if value!=EXPECTED:raise ValueError('Exact admitted local node editor profile required')
 preset=value['presets'];path=Path(preset['path']);manifest=Path(preset['manifest']['path'])
 if (not path.is_absolute() or path.is_symlink() or manifest!=path/'manifest.json'
     or hashlib.sha256(manifest.read_bytes()).hexdigest()!=preset['manifest']['sha256']):
  raise ValueError('Native editor preset identity changed')
 return deepcopy(value)

class NativeEditSite(EditorSite):
 def start_frontend(self,port):
  super().start_frontend(port)
  if self.reset_guard is not None:raise ValueError('Native write audit must precede reset baseline')
  self.app_sql(INSTALL)

def new_site(root,logs,profile):
 profile=validate_profile(profile)
 return NativeEditSite(root,logs,account=profile['account'],presets=profile['presets']['path'])
