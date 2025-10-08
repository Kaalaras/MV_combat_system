"""Compatibility layer re-exporting the ECS-based movement system."""

from __future__ import annotations

from ecs.systems.movement import MovementSystem

__all__ = ["MovementSystem"]
