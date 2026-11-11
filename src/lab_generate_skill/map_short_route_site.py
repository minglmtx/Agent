"""Opt-in route-preserving compact links on the existing native Map website."""
import hashlib
from .map_query_site import IsolatedMapQuerySite
from .map_short_route import patch
from .io_utils import atomic_write_json as save


class IsolatedMapShortRouteSite(IsolatedMapQuerySite):
    def __init__(self,root,logs):
        self.short_route_installed=False
        super().__init__(root,logs,with_tiles=True,with_geographic_baseline=True,
                         track_changes=True,native_share_observer=True)

    def launch(self,command,name):
        if name=='rails_server'and not self.short_route_installed:
            app=self.state/'frontend/app';a=app/'app/assets/javascripts/leaflet.map.js';b=app/'app/controllers/site_controller.rb'
            js,ruby=patch(a.read_text(),b.read_text());a.write_text(js);b.write_text(ruby)
            save(self.logs/'short-route-extension.json',dict(version='local-compact-route-v1',
                original_benchmark_equivalence=False,source='current public route URL and visible native route',
                coordinate_decimals=6,mutable_token_database=False,
                source_hashes={str(p.relative_to(app)):hashlib.sha256(p.read_bytes()).hexdigest()for p in (a,b)}))
            self.short_route_installed=True
        return super().launch(command,name)
