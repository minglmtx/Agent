"""Actual BrowserGym leaf, owned by one worker process/thread and original scope.

Start attaches the event buffer before the task's first goto. Step uses strict
single actions and exact public observations. This synchronous leaf MUST run
inside external process supervision for production hard deadlines; checkpoints
and Playwright timeouts do not prove parent-death or uninterruptible-I/O safety.
All publication and task judging are outside this file. Failures quarantine the
engine; close independently attempts every owned component and retains errors.
"""

import os
from pathlib import Path
import threading
from typing import Any, Literal
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.browser_authority import BrowserAuthority
from lab_generate_skill.ports.lifecycle import Clock, OperationControl
from lab_generate_skill.ports.browser_initialization import BrowserInitializer
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.ports.browser_capture import BrowserPageCollector
from lab_generate_skill.ports.browser_task_files import BrowserTaskFiles
from lab_generate_skill.ports.browser_process import BrowserProcessCollector
from .actions import action_set, map_action, validate_action
from .events import BrowserEvents
from .observation import project
from .public_viewport import public_viewport
from lab_generate_skill.domain.observation_viewport import ObservationViewport


class BrowserGymEngine:
    def __init__(
        self,
        spec: BrowserSessionSpec,
        authority: BrowserAuthority,
        clock: Clock,
        initializer: BrowserInitializer,
        *,
        collector: BrowserPageCollector | None = None,
        capture_public_viewport: bool = False,
        task_files: BrowserTaskFiles | None = None,
        process_collector: BrowserProcessCollector | None = None,
    ) -> None:
        self.spec = BrowserSessionSpec.model_validate(spec)
        self.authority, self.clock = authority, clock
        self.capture_public_viewport = capture_public_viewport
        self.viewport: ObservationViewport | None = None
        self.collector = collector
        self.task_files = task_files
        if process_collector is not None and not isinstance(
            process_collector, BrowserProcessCollector
        ):
            raise TypeError("Process collector must implement the complete lifecycle")
        self.process_collector = process_collector
        self.last_capture: BrowserCaptureResult | None = None
        self.initializer = initializer
        self.owner = (os.getpid(), threading.get_ident())
        self.state: Literal[
            "new", "busy", "ready", "terminal", "quarantined", "closed"
        ] = "new"
        self.events = BrowserEvents(spec.max_events)
        self.env: Any = None
        self.driver: Any = None
        self.last_readout: BrowserReadout | None = None
        self.last_native_return: tuple[dict[str, Any], float, bool, bool] | None = None
        self.sequence = 0
        self.used_actions: set[str] = set()
        self.used_operations: set[str] = set()
        self._actions: Any = None
        self._timeout = spec.action_timeout_ms

    def _check(
        self, operation: OperationContext, *, cleanup: bool = False
    ) -> OperationContext:
        operation = OperationContext.model_validate(operation)
        if (os.getpid(), threading.get_ident()) != self.owner:
            raise OwnershipConflict(
                "Browser capability belongs to its original worker/thread"
            )
        scope = self.spec.scope
        if (operation.run_id, operation.owner_id, operation.attempt_id) != (
            scope.owner.run_id,
            scope.owner.owner_id,
            scope.attempt_id,
        ):
            raise OwnershipConflict("Browser operation changed original scope")
        if operation.mode != ("cleanup" if cleanup else "execute"):
            raise OwnershipConflict("Browser operation has the wrong phase")
        if self.state == "busy":
            raise InvalidTransition("Browser operation is already active")
        return operation

    def _readout(
        self,
        raw: dict[str, Any],
        reward: float,
        terminated: bool,
        truncated: bool,
        protocol_terminal: bool,
        operation: OperationContext,
        action: BrowserAction | None,
        control: OperationControl,
    ) -> BrowserReadout:
        self.events.check()
        self.viewport = None
        observed = project(raw, self.spec, self.sequence, self.clock.utcnow())
        if self.capture_public_viewport:
            observed, self.viewport = public_viewport(raw, observed)
        result = BrowserReadout(
            schema_version=(
                "browser-initial-return/1"
                if action is None
                else "browser-step-return/1"
            ),
            scope=self.spec.scope,
            operation=operation,
            action=action,
            observation=observed,
            events=tuple(self.events.events),
            environment_reward=float(reward),
            terminated=bool(terminated),
            truncated=bool(truncated),
            protocol_terminal=protocol_terminal,
        )
        self.last_readout = result
        if self.process_collector is not None:
            self.process_collector.observe(self.env.page, result, control)
        return result

    def start(
        self, operation: OperationContext, *, control: OperationControl
    ) -> BrowserReadout:
        operation = self._check(operation)
        if self.state != "new":
            raise InvalidTransition(
                "Browser start is one-use; no reset/restart fallback"
            )
        control.checkpoint()
        self.authority.verify(self.spec, "start", None, operation, control)
        self.state = "busy"
        self.used_operations.add(operation.operation_id)
        try:
            if self.task_files is not None:
                self.task_files.prepare(self.spec, control)
            import browsergym.core as core  # type: ignore[import-untyped]
            from browsergym.core.env import BrowserEnv  # type: ignore[import-untyped]
            from browsergym.core.task import OpenEndedTask  # type: ignore[import-untyped]

            if core.__version__ != "0.14.3" or core._PLAYWRIGHT is not None:
                raise RuntimeError(
                    "Requires pinned BrowserGym 0.14.3 in an unused isolated worker"
                )
            self._actions = action_set(self._timeout)
            if not set(self.spec.task.allowed_actions) <= set(self._actions.action_set):
                raise ValueError("Public task declares unsupported BrowserGym actions")
            self.driver = core._get_global_playwright()
            if (
                Path(self.driver.chromium.executable_path).resolve()
                != Path(self.spec.chromium_executable).resolve()
            ):
                raise OwnershipConflict(
                    "Playwright browser asset differs from frozen executable"
                )

            def task_entrypoint(seed: int) -> Any:
                task = OpenEndedTask(
                    seed, self.spec.task.start_url, self.spec.task.goal
                )

                def before_navigation(page: Any) -> Any:
                    self.events.attach(page.context)
                    self.events.add("before_navigation", url=self.spec.task.start_url)
                    control.checkpoint()
                    if self.process_collector is not None:
                        self.process_collector.attach(page, self.spec, control)
                    self.initializer.setup(page, self.spec.task, control)
                    return self.spec.task.goal, {}

                task.setup = before_navigation
                return task

            self.env = BrowserEnv(
                task_entrypoint=task_entrypoint,
                headless=True,
                wait_for_user_message=False,
                timeout=self.spec.action_timeout_ms,
                action_mapping=lambda payload: map_action(
                    self._actions, payload, self._timeout
                ),
                pw_chromium_kwargs={"executable_path": self.spec.chromium_executable},
            )
            control.checkpoint()
            raw, _ = self.env.reset(seed=self.spec.seed)
            self.last_native_return = (raw, 0.0, False, False)
            result = self._readout(
                raw, 0.0, False, False, False, operation, None, control
            )
            result.observation.check_initial(
                self.spec.task.identity, self.spec.scope.context_id
            )
            control.checkpoint()
            self.state = "ready"
            return result
        except BaseException:
            self.state = "quarantined"
            raise

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> BrowserReadout:
        operation = self._check(operation)
        action = BrowserAction.model_validate(action)
        if self.state != "ready":
            raise InvalidTransition("Browser is not ready for another action")
        validate_action(action, self.spec.task)
        if (
            action.action_id in self.used_actions
            or operation.operation_id in self.used_operations
        ):
            raise InvalidTransition(
                "Original browser action/operation cannot be repeated"
            )
        control.checkpoint()
        self.authority.verify(self.spec, "step", action, operation, control)
        self.state = "busy"
        self.used_actions.add(action.action_id)
        self.used_operations.add(operation.operation_id)
        self.last_readout = None
        self.last_native_return = None
        try:
            if self.process_collector is not None:
                self.process_collector.before_action(control)
            if action.name == "upload_file":
                if self.task_files is None:
                    raise OwnershipConflict(
                        "Upload requires declared public task files"
                    )
                self.task_files.validate(action, control)
            self._timeout = max(
                1, min(self.spec.action_timeout_ms, int(control.checkpoint() * 1000))
            )
            self._actions = action_set(self._timeout)
            map_action(self._actions, action.payload, self._timeout)
            self.events.add("before_action", action_id=action.action_id)
            raw, reward, terminated, truncated, _ = self.env.step(action.payload)
            self.last_native_return = (raw, reward, terminated, truncated)
            self.events.add("after_action", action_id=action.action_id)
            terminal = action.name in ("send_msg_to_user", "report_infeasible")
            if terminated or truncated or terminal:
                self.events.add("terminal", action_id=action.action_id)
            self.sequence += 1
            result = self._readout(
                raw, reward, terminated, truncated, terminal, operation, action, control
            )
            # Do not erase an obtained environment return because time expired.
            self.state = "terminal" if terminated or truncated or terminal else "ready"
            return result
        except BaseException:
            self.state = "quarantined"
            raise

    def capture_page(
        self, request: BrowserCaptureRequest, *, control: OperationControl
    ) -> BrowserCaptureResult:
        request = BrowserCaptureRequest.model_validate(request)
        self._check(request.operation)
        if (
            self.state not in ("ready", "terminal")
            or self.last_readout is None
            or self.collector is None
        ):
            raise InvalidTransition(
                "Capture requires original active browser and selected collector"
            )
        request.check_readout(self.spec, self.last_readout)
        if request.operation.operation_id in self.used_operations:
            raise InvalidTransition("Browser capture operation already consumed")
        control.checkpoint()
        previous = self.state
        self.state = "busy"
        self.used_operations.add(request.operation.operation_id)
        self.last_capture = None
        try:
            payload = self.collector.collect(
                self.env.page, request.collector_id, request.collector_version, control
            )
            result = BrowserCaptureResult(
                request_sha256=request.digest,
                captured_at=self.clock.utcnow(),
                private_result=payload,
            )
            self.last_capture = result
            control.checkpoint()
            self.state = previous
            return result
        except BaseException:
            self.state = "quarantined"
            raise

    def quarantine(self) -> None:
        self.state = "quarantined"

    def close(self, operation: OperationContext, *, control: OperationControl) -> None:
        operation = self._check(operation, cleanup=True)
        if self.state == "closed":
            return
        control.checkpoint()
        self.authority.verify(self.spec, "close", None, operation, control)
        self.state = "busy"
        errors: list[BaseException] = []
        if self.process_collector is not None:
            try:
                self.process_collector.close(control)
                self.process_collector = None
            except BaseException as error:
                errors.append(error)
        try:
            self.events.close()
        except BaseException as error:
            errors.append(error)
        if self.env is not None:
            for name, method in (
                ("task", "teardown"),
                ("chat", "close"),
                ("context", "close"),
                ("browser", "close"),
            ):
                value = getattr(self.env, name, None)
                if value is not None:
                    try:
                        control.checkpoint()
                        getattr(value, method)()
                        setattr(self.env, name, None)
                    except BaseException as error:
                        errors.append(error)
        if self.driver is not None:
            try:
                control.checkpoint()
                self.driver.stop()
                import browsergym.core as core

                if core._PLAYWRIGHT is self.driver:
                    core._set_global_playwright(None)
                self.driver = None
            except BaseException as error:
                errors.append(error)
        if self.task_files is not None:
            try:
                self.task_files.close(control)
            except BaseException as error:
                errors.append(error)
        self.state = "quarantined" if errors else "closed"
        if errors:
            raise BaseExceptionGroup("Browser close incomplete", errors)
