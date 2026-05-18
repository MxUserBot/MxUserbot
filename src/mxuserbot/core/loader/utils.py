# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import ast
import hashlib
import re

from .constants import FORBIDDEN_CLIENT_ATTRS


def _parse_cron(s: str) -> float:
    s = s.strip().lower()
    m = re.match(r'^(\d+)\s*([smh])$', s)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        if unit == 's': return float(val)
        if unit == 'm': return float(val * 60)
        if unit == 'h': return float(val * 3600)
    parts = s.split()
    if len(parts) >= 1 and re.match(r'^\*/\d+$', parts[0]):
        return float(int(parts[0][2:]) * 60)
    if len(parts) >= 2 and parts[0] == '0' and parts[1] == '*':
        return 3600.0
    return 60.0


def _calc_module_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()


FORBIDDEN_EVAL = frozenset({"eval", "exec", "__import__"})


def _check_community_source(source: str, module_name: str):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CLIENT_ATTRS:
            raise PermissionError(
                f"Module '{module_name}': forbidden attribute '{node.attr}'"
            )

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_EVAL:
                raise PermissionError(
                    f"Module '{module_name}': forbidden call '{node.func.id}'"
                )
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in FORBIDDEN_EVAL:
                    raise PermissionError(
                        f"Module '{module_name}': forbidden call '{node.func.attr}'"
                    )
                if node.func.attr == "getattr":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            if arg.value in FORBIDDEN_CLIENT_ATTRS:
                                raise PermissionError(
                                    f"Module '{module_name}': forbidden getattr('{arg.value}')"
                                )


def _parse_deps_from_code(code: str) -> tuple[list[str], bool]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return [], False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Meta":
            deps = []
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        if getattr(t, 'id', '') == 'dependencies':
                            if isinstance(stmt.value, (ast.List, ast.Tuple)):
                                deps = [
                                    elt.value for elt in stmt.value.elts
                                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                                ]
            return deps, True
    return [], False
