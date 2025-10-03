"""Minimal hot-seat console controller implementation."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from core.actions.intent import ActionIntent, TargetSpec
from core.events import topics


class HotSeatCLIController:
    """Simple console driven controller for local multiplayer hot-seat games."""

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._event_bus: Any = None
        self._input = input_fn or input
        self._output = output_fn or print
        self._pending_actor: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API expected by the InputController protocol
    # ------------------------------------------------------------------
    def bind(self, event_bus: Any) -> None:
        """Subscribe controller handlers to the provided event bus."""

        self._event_bus = event_bus
        event_bus.subscribe(topics.REQUEST_ACTIONS, self._handle_request_actions)
        event_bus.subscribe(topics.ACTIONS_AVAILABLE, self._handle_actions_available)
        event_bus.subscribe(topics.REACTION_WINDOW_OPENED, self._handle_reaction_window)

    def on_request_actions(self, actor_id: str) -> None:  # pragma: no cover - IO only
        self._output(f"[HotSeat] Awaiting available actions for actor '{actor_id}'.")

    def on_reaction_prompt(self, reaction_context: Mapping[str, Any]) -> None:  # pragma: no cover - IO only
        self._output("[HotSeat] Reaction window opened.")
        options = list(reaction_context.get("options", []))
        if not options:
            self._output("  (no reactions available)")
            return
        for idx, option in enumerate(options, start=1):
            label = option.get("name") or option.get("id") or f"Option {idx}"
            self._output(f"  {idx}. {label}")

    # ------------------------------------------------------------------
    # Internal event handlers
    # ------------------------------------------------------------------
    def _handle_request_actions(self, event: Mapping[str, Any]) -> None:
        actor_id = str(event.get("actor_id"))
        self._pending_actor = actor_id
        self.on_request_actions(actor_id)

    def _handle_actions_available(self, event: Mapping[str, Any]) -> None:
        if not self._event_bus:
            return

        actor_id = str(event.get("actor_id"))
        if self._pending_actor is not None and actor_id != self._pending_actor:
            return

        actions = list(event.get("actions", []))
        if not actions:
            self._output("[HotSeat] No actions available.")
            return

        self._output(f"[HotSeat] Available actions for {actor_id}:")
        for idx, action in enumerate(actions, start=1):
            label = action.get("name") or action.get("id") or f"Action {idx}"
            self._output(f"  {idx}. {label}")

        choice = self._prompt_index(len(actions), prompt="Select action (or 0 to skip): ")
        if choice <= 0:
            self._output("[HotSeat] Action selection skipped.")
            return

        action_data = actions[choice - 1]
        targets = self._prompt_targets(action_data)
        params = dict(action_data.get("default_params", {}))

        intent = ActionIntent(
            actor_id=actor_id,
            action_id=str(action_data.get("id") or action_data.get("name")),
            targets=tuple(targets),
            params=params,
            source_player_id=event.get("source_player_id"),
            client_tx_id=event.get("client_tx_id"),
        )

        self._publish(topics.INTENT_SUBMITTED, {"intent": intent.to_dict()})

    def _handle_reaction_window(self, event: Mapping[str, Any]) -> None:
        if not self._event_bus:
            return

        actor_id = event.get("actor_id")
        options = list(event.get("options", []))
        context = {"options": options}
        self.on_reaction_prompt(context)

        if not options:
            self._publish(
                topics.REACTION_DECLARED,
                {"actor_id": actor_id, "reaction": None, "passed": True},
            )
            return

        choice = self._prompt_index(len(options), prompt="Select reaction (0 to pass): ")
        if choice <= 0:
            payload = {"actor_id": actor_id, "reaction": None, "passed": True}
        else:
            payload = {
                "actor_id": actor_id,
                "reaction": options[choice - 1],
                "passed": False,
            }

        self._publish(topics.REACTION_DECLARED, payload)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _prompt_index(self, upper_bound: int, *, prompt: str) -> int:
        while True:
            raw_value = self._input(prompt).strip()
            if not raw_value:
                return 0
            if raw_value.isdigit():
                value = int(raw_value)
                if 0 <= value <= upper_bound:
                    return value
            self._output(f"Please enter a number between 0 and {upper_bound}.")

    def _prompt_targets(self, action_data: Mapping[str, Any]) -> list[TargetSpec]:
        targets: list[TargetSpec] = []
        target_descriptors = action_data.get("targets") or action_data.get("targeting")
        if not target_descriptors:
            return targets

        for descriptor in target_descriptors:
            kind = descriptor.get("kind") or descriptor.get("type")
            prompt = descriptor.get("prompt") or f"Provide target for {kind}: "
            user_input = self._input(prompt).strip()
            if not user_input:
                continue

            if kind == "self":
                targets.append(TargetSpec.self())
            elif kind == "entity":
                targets.append(TargetSpec.entity(user_input))
            elif kind == "tile":
                coords = tuple(int(part) for part in user_input.split(","))
                targets.append(TargetSpec.tile(coords))
            elif kind == "area":
                coords_part, _, radius_part = user_input.partition(";")
                coords = tuple(int(part) for part in coords_part.split(","))
                radius = int(radius_part.strip() or descriptor.get("radius", 0))
                shape = descriptor.get("shape", "circle")
                targets.append(TargetSpec.area(coords, shape=shape, radius=radius))
            else:
                targets.append(
                    TargetSpec(kind=str(kind), extra={"value": user_input})
                )

        return targets

    def _publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        if not self._event_bus:
            raise RuntimeError("Controller must be bound to an event bus before use.")
        self._event_bus.publish(topic, payload)


__all__ = ["HotSeatCLIController"]

