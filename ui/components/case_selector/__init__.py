from __future__ import annotations

from typing import Any

import streamlit.components.v1 as components


_case_selector = components.declare_component(
    "dicloak_case_selector",
    path=__path__[0],
)


def render_case_selector(**kwargs: Any) -> Any:
    return _case_selector(**kwargs)
