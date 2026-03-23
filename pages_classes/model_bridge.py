"""
Resolve each oTree app's ``models`` module from a Player (or Subsession/Group) instance.

``pages_classes`` lives at the project root, so it must not use ``from ..models import``.
At runtime, ``type(player).__module__`` is e.g. ``PD_llm_delegation_1st.models``.
"""

from __future__ import annotations

import importlib
import types
from typing import Any


def get_models_module(obj: Any):
    """Return the app's ``models`` module (same module that defines ``Constants``, ``Player``, …)."""
    cls = obj if isinstance(obj, type) else type(obj)
    mod_name = getattr(cls, "__module__", None)
    if not mod_name:
        raise TypeError(f"Cannot resolve models module from {obj!r}")
    return importlib.import_module(mod_name)


def get_constants(obj: Any):
    """Return this app's ``Constants`` class."""
    return get_models_module(obj).Constants


def app_package_name(obj: Any) -> str:
    """App package for template paths, e.g. ``PD_rule_based_delegation_2nd``."""
    mod_name = getattr(type(obj) if not isinstance(obj, type) else obj, "__module__", "")
    return mod_name.rsplit(".", 1)[0]


def app_models(player) -> types.SimpleNamespace:
    """
    Per-request view of the current app's models module with optional helpers.

    Apps that omit results-display cache helpers still work: fallbacks use DB paths or
    plain ``get_opponent_in_round`` (no round cache).
    """
    m = get_models_module(player)
    get_opp_cached = getattr(
        m,
        "get_opponent_in_round_cached",
        lambda pl, rn, cache: m.get_opponent_in_round(pl, rn),
    )
    return types.SimpleNamespace(
        Constants=m.Constants,
        compute_round_robin_assignments=m.compute_round_robin_assignments,
        run_payoffs_for_matching_group=m.run_payoffs_for_matching_group,
        get_opponent_in_round=m.get_opponent_in_round,
        get_opponent_in_round_cached=get_opp_cached,
        get_results_display_from_cache=getattr(
            m, "get_results_display_from_cache", lambda participant, part: None
        ),
        _log_cache_miss=getattr(m, "_log_cache_miss", lambda *a, **k: None),
    )
