"""Test bootstrap: ensure package root is on sys.path.

This allows absolute imports like `core.game_state` and `entities.default_entities.*`
which assume the working directory is the inner package root.
"""
import sys, os
PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

