# -*- coding: utf-8 -*-
"""stukach_core — DCC-free mesh validation core.

Pure Python (+ numpy/scipy where noted). No maya.cmds, no bpy.
DCC adapters build a MeshSnapshot from their own API and render Finding
element indices into native component strings.

Public API:
    MeshSnapshot, Finding, run_checks, RULES
"""
from .model import MeshSnapshot, Finding, edge_length
from .registry import RULES, run_checks

__all__ = ["MeshSnapshot", "Finding", "edge_length",
           "RULES", "run_checks"]
__version__ = "0.1.0"
