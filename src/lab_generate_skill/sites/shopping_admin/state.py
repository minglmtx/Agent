"""Compose original DB/file/cache/search recovery under mandatory delegated admission.

Preflight all snapshots before the first restore mutation. No implicit retries,
rollback, service replacement or deletion of failed evidence. Failed save/restore
quarantines this object; physical resource cleanup belongs to its outer owner.
"""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .state_contract import AdminStatePlan, AdminStateSnapshot, AdminStateRestored
from .state_authority import AdminStateAuthority
from .database import AdminDatabase
from .artifacts import AdminArtifacts
from .caches import AdminCaches
from .search import AdminSearch
from .search_authority import AdminSearchAuthority


class AdminState:
    def __init__(
        self,
        plan: AdminStatePlan,
        commands: NativeCommands,
        authority: AdminStateAuthority,
        search_authority: AdminSearchAuthority,
    ) -> None:
        self.plan = AdminStatePlan.model_validate(plan)
        self.authority = authority
        self.database = AdminDatabase(self.plan.service.layout, commands)
        self.artifacts = AdminArtifacts(self.plan.artifacts)
        self.caches = AdminCaches(self.plan.service, commands)
        self.search = AdminSearch(self.plan.service, commands, search_authority)
        self.save_attempted = False
        self.restore_attempted = False
        self.quarantined = False
        self.busy = False

    def _available(self) -> None:
        if self.busy or self.quarantined:
            raise RuntimeError("Original state operation busy or quarantined")

    def save(self, control: OperationControl) -> AdminStateSnapshot:
        self._available()
        if self.save_attempted:
            raise RuntimeError("Snapshot save already attempted")
        control.checkpoint()
        self.busy = True
        database = artifacts = search = None
        try:
            self.authority.verify(self.plan, "save", None, control)
            self.save_attempted = True
            search = self.search.save(control)
            database = self.database.save(control)
            artifacts = self.artifacts.save(control)
            result = AdminStateSnapshot(
                plan=self.plan, database=database, artifacts=artifacts, search=search
            )
            control.checkpoint()
            return result
        except BaseException as error:
            if self.save_attempted:
                self.quarantined = True
            setattr(error, "admin_database_snapshot", database)
            setattr(error, "admin_artifact_snapshot", artifacts)
            setattr(error, "admin_search_snapshot", search or self.search.saved)
            raise
        finally:
            self.busy = False

    def restore(
        self, snapshot: AdminStateSnapshot, control: OperationControl
    ) -> AdminStateRestored:
        self._available()
        if self.restore_attempted:
            raise RuntimeError("Restore already attempted")
        snapshot = AdminStateSnapshot.model_validate(snapshot)
        if snapshot.plan != self.plan:
            raise ValueError("Restore must preserve exact original plan")
        control.checkpoint()
        self.busy = True
        mutation = False
        completed: list[str] = []
        try:
            self.authority.verify(self.plan, "restore", snapshot, control)
            self.database.verify(snapshot.database, control)
            self.artifacts.verify(snapshot.artifacts, control)
            self.search.preflight_restore(snapshot.search, control)
            control.checkpoint()
            self.restore_attempted = True
            mutation = True
            database = self.database.restore(snapshot.database, control)
            completed.append("database")
            artifacts = self.artifacts.restore(snapshot.artifacts, control)
            completed.append("declared_artifacts")
            cache = self.caches.reset(control)
            completed.append("application_cache_and_redis")
            search = self.search.restore(snapshot.search, control)
            completed.append("search")
            result = AdminStateRestored(
                snapshot_sha256=snapshot.digest,
                database=database,
                artifacts=artifacts,
                cache=cache,
                search=search,
            )
            control.checkpoint()
            return result
        except BaseException as error:
            # Even a preflight error leaves baseline integrity unproven; no reuse.
            self.quarantined = True
            setattr(error, "admin_restore_mutation_attempted", mutation)
            setattr(error, "admin_restore_completed", tuple(completed))
            setattr(error, "admin_state_snapshot", snapshot)
            raise
        finally:
            self.busy = False
