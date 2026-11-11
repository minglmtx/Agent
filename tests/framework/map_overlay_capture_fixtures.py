"""Full synthetic surface/route facts retained by the original native collector."""

from copy import deepcopy
from typing import Any, Literal
from urllib.parse import urlsplit
import pytest
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.native_surface_capture import NativeSurfaceCapture
from lab_generate_skill.sites.map.native_surface_script import COMBINED_READ
from test_map_overlay_rules import surfaces


def full_surface_fixture(patch: pytest.MonkeyPatch) -> None:
    original = NativeSurfaceCapture.capture

    def capture(
        self: NativeSurfaceCapture,
        page: Any,
        readout: BrowserReadout,
        control: OperationControl,
        *,
        phase: Literal["unique_return", "terminal"],
    ) -> ReleaseFile:
        before, after, route = surfaces()
        value = deepcopy(after if phase == "terminal" else before)
        parsed = urlsplit(page.url)
        origin = parsed.scheme + "://" + parsed.netloc
        value["url"] = page.url
        value["native_long_link"] = (
            origin
            + "/#map=15/40.77/-73.97"
            + ("&layers=D" if phase == "terminal" else "")
        )
        evaluate = page.evaluate

        def read(program: str, args: Any = None) -> Any:
            return (
                dict(surface=value, route=route)
                if program == COMBINED_READ
                else evaluate(program, args)
            )

        with patch.context() as local:
            local.setattr(page, "evaluate", read)
            return original(self, page, readout, control, phase=phase)

    patch.setattr(NativeSurfaceCapture, "capture", capture)
