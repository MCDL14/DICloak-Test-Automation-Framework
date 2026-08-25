from __future__ import annotations

from typing import Any

import streamlit.components.v1 as components


_case_progress = components.declare_component(
    "dicloak_case_progress",
    path=__path__[0],
)


def render_case_progress(**kwargs: Any) -> Any:
    return _case_progress(**kwargs)
