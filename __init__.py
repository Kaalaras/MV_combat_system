"""MV_combat_system package root.

Provides backward-compatible alias modules so existing code/tests that use
`import core...` or `import ecs...` continue to function when the
package is installed (canonical path is MV_combat_system.core, etc.).
"""
from importlib import import_module
import sys as _sys

__all__ = ["core", "ecs", "entities", "utils", "interface"]
__version__ = "0.1.0"

for _name in __all__:
    try:
        _mod = import_module(f"MV_combat_system.{_name}")
        # Expose as attribute of this package
        globals()[_name] = _mod  # type: ignore
        # Provide top-level alias if not already defined
        if _name not in _sys.modules:
            _sys.modules[_name] = _mod
    except ModuleNotFoundError:  # pragma: no cover - optional subpackages
        pass

del import_module, _sys, _name, _mod

