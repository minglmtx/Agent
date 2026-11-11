"""One isolated native tile database/style reused by an owned PNG endpoint."""
from pathlib import Path
import hashlib,shutil
from .map_query_site import IsolatedMapQuerySite
from .map_raster_frontend import patch
from .io_utils import atomic_write_json as save


class IsolatedMapRasterSite(IsolatedMapQuerySite):
    def __init__(self,root,logs,*,retain_renders=False,short_routes=False,allow_pdf=False,query_policy='default'):
        if query_policy not in ('default','stable-scan'):
            raise ValueError('Unsupported renderer query policy')
        self.query_policy=query_policy
        self.allow_pdf=allow_pdf
        self.retain_renders=retain_renders
        self.short_routes=short_routes
        self.raster_lease=None;self.raster_installed=False
        super().__init__(root,logs,with_tiles=True,with_geographic_baseline=True,
                         track_changes=True,native_share_observer=True,native_short_routes=short_routes)

    def launch(self,command,name):
        if name=='rails_server'and not self.raster_installed:
            from .admin_ports import PortLease
            self.raster_lease=PortLease(count=1)
            state=self.state/'tiles';port=self.raster_lease.ports[0]
            source=Path(__file__).resolve().parents[2]
            shutil.copyfile(source/'scripts/serve_map_raster.py',state/'serve_map_raster.py')
            shutil.copyfile(source/'src/lab_generate_skill/map_raster_request.py',state/'map_raster_request.py')
            self.raster_url=f'http://127.0.0.1:{port}/render'
            super().launch(self.flags(state)+[str(self.images/'tiles.sif'),'python3','-B','/state/serve_map_raster.py','--port',str(port),'--query-policy',self.query_policy]+(['--retain-renders']if self.retain_renders else [])+(['--allow-pdf']if self.allow_pdf else []),'native_raster')
            self.wait_http(f'http://127.0.0.1:{port}/health',45)
            app=self.state/'frontend/app'
            a=app/'app/controllers/export_controller.rb';b=app/'app/assets/javascripts/leaflet.share.js'
            olda,oldb=a.read_text(),b.read_text();newa,newb=patch(olda,oldb,self.raster_url,allow_pdf=self.allow_pdf);a.write_text(newa);b.write_text(newb)
            save(self.logs/'local-raster-extension.json',dict(version='native-local-png-pdf-export-candidate-v1' if self.allow_pdf else 'native-local-png-export-v1',
                synthetic_service=True,original_benchmark_equivalence=False,public_route_from_current_page=True,
                upstream_style_unchanged=True,formats=['png','pdf'] if self.allow_pdf else ['png'],external_requests=False,
                source_hashes={str(p.relative_to(app)):hashlib.sha256(p.read_bytes()).hexdigest()for p in (a,b)}))
            self.raster_installed=True
        return super().launch(command,name)

    def __exit__(self,*args):
        try:
            if self.temporary is not None:
                receipts=self.state/'tiles/raster-receipts.jsonl'
                if receipts.exists():shutil.copyfile(receipts,self.logs/'raster-receipts.jsonl')
                evidence=self.state/'tiles/raster-evidence'
                if self.retain_renders and evidence.exists():shutil.copytree(evidence,self.logs/'raster-evidence',dirs_exist_ok=True)
        finally:
            try:super().__exit__(*args)
            finally:
                if self.raster_lease is not None:
                    self.raster_lease.close();self.raster_lease=None
