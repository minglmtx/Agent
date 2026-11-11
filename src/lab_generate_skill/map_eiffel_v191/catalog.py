"""Expose one independently reviewed search source without changing its scope."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,os,tempfile
from lab_generate_skill.provider_review_catalog import identity
from .adapter import Adapter
from .evaluate import SOURCE


class EiffelCatalog:
    def __init__(self,config,*,project):
        self.config=deepcopy(config)
        self.project=Path(project).resolve()
        self.files={}
        self.closed=False
        self.temporary=None
        self.adapter=None
        self.sources={}
        self.descriptors={}
        self.config_digest=self.digest(config)
        try:
            if config.get("version")!="reviewed-eiffel-search-catalog-v191" or config.get("source_ids")!=[SOURCE]:
                raise ValueError("Exactly the reviewed Eiffel source required")
            required={"src/lab_generate_skill/map_eiffel_v191/"+name for name in (
                "__init__.py","adapter.py","evaluate.py","search_hooks.py","archive_reader.py","catalog.py","bridge.py")}
            required.add("src/lab_generate_skill/reviewed_map_registry.py")
            if not required<=config["runtime_files"].keys():
                raise ValueError("Complete current Eiffel integration required")
            for name,digest in config["runtime_files"].items():
                if Path(name).is_absolute()or ".."in Path(name).parts:
                    raise ValueError("Contained runtime member required")
                self.read(dict(path=str(self.project/name),sha256=digest),parse=False)
            relocation=self.read(config["relocation_review"])
            if not relocation.get("passed")or relocation.get("only_import_paths_changed")is not True:
                raise ValueError("Exact qualified implementation relocation required")
            for name,row in relocation["files"].items():
                current=self.read(dict(path=str(self.project/row["relative"]),sha256=row["current_sha256"]),parse=False)
                previous=self.read(row["previous"],parse=False)
                projected=current.decode()
                for module in ("archive_reader","evaluate","search_hooks"):
                    projected=projected.replace("from ."+module+" import ","from "+module+" import ")
                if projected.encode()!=previous:
                    raise ValueError("Search semantics changed beyond import relocation")
            qualified=self.read(config["qualified_entry_config"])
            entry_review=self.read(config["qualified_entry_review"])
            actual=self.read(config["actor_review"])
            if (not entry_review["passed"]or entry_review["actual_control_native_results_replayed"]!=6
                    or not actual.get("passed")or not actual.get("source_result_accepted")
                    or not actual.get("ready_for_publication")
                    or actual["source_task_id"]!=SOURCE or actual["actual_actor_attempts"]!=1
                    or actual["judgment"]["status"]not in("success","failure")
                    or actual["entry_review"]!=config["qualified_entry_review"]):
                raise ValueError("Actual closed first Actor and native input proof required")
            for ref in (actual["plan"],actual["raw_archive"],actual["ordinary_archive"]):
                self.read(ref,parse=False)
            if not os.environ.get("SLURM_JOB_ID")or not os.environ.get("TMPDIR"):
                raise ValueError("Native retained evidence requires allocated scratch")
            self.temporary=tempfile.TemporaryDirectory(prefix="eiffel-catalog-",dir=os.environ["TMPDIR"])
            self.adapter=Adapter(qualified,project=self.project,work=Path(self.temporary.name)/"controls")
            c=self.adapter.c
            if c["source_task_id"]!=SOURCE or actual["task_id"]!=c["task_id"]:
                raise ValueError("Actual Actor task differs from current source")
            self.sources[SOURCE]=dict(candidate=deepcopy(c),
                admission=self.adapter.require_admission(c,self.adapter.descriptor))
            self.descriptors[SOURCE]=deepcopy(self.adapter.descriptor)
            self.require_current()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def digest(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def read(self,ref,*,parse=True):
        path=Path(ref["path"])
        before=identity(path)
        raw=path.read_bytes()
        if not path.is_absolute()or path.is_symlink()or identity(path)!=before or hashlib.sha256(raw).hexdigest()!=ref["sha256"]:
            raise ValueError("Eiffel native evidence or execution code changed")
        self.files[path]=before
        return json.loads(raw)if parse else raw

    def require_current(self):
        if (self.closed or self.digest(self.config)!=self.config_digest
                or any(identity(p)!=value for p,value in self.files.items())):
            raise ValueError("Eiffel catalog changed or closed")
        if self.adapter is not None:self.adapter.require_current()

    def resolve(self,sid,descriptor):
        self.require_current()
        if sid!=SOURCE or descriptor is not None and descriptor!=self.descriptors[sid]:
            raise ValueError("Exact reviewed Eiffel descriptor required")
        return dict(**deepcopy(self.sources[sid]),descriptor=deepcopy(self.descriptors[sid]),adapter=self.adapter)

    def close(self):
        self.closed=True
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary=None
