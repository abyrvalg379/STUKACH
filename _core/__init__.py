# -*- coding: utf-8 -*-
"""stukach_core — DCC-free mesh validation core.

Pure Python (+ numpy where noted). No maya.cmds, no bpy.
DCC adapters build a MeshSnapshot from their own API and render Finding
element indices into native component strings.

Public API:
    MeshSnapshot, Finding, run_checks, RULES,
    naming (contract + hygiene validators), verdict/merge
"""
from .model import MeshSnapshot, Finding, edge_length
from .checks import topology, surface, symmetry, scene, uv, transform
from .registry import RULES, run_checks
from . import naming
from .verdict import verdict, merge

__all__ = ["MeshSnapshot", "Finding", "edge_length",
           "RULES", "run_checks", "naming", "verdict", "merge"]
__version__ = "0.8.0"
