"""Injected preparation guard; the adapter never imports orchestration code."""

from typing import Callable
from lab_generate_skill.domain.actor_execution_window import ActorGenerationWindow
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl

GenerationPreparationControlFactory = Callable[
    [OperationContext, ActorGenerationWindow | None, OperationControl], OperationControl
]
