"""Minimal hot-seat console controller implementation."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Optional, Protocol

from core.actions.intent import ActionIntent, TargetSpec
from core.events import topics


class EventBusLike(Protocol):
    def subscribe(self, event_type: str, handler: Callable[..., None]) -> None:
        ...

    def publish(self, event_type: str, /, **payload: Any) -> None:
        ...


class HotSeatCLIController:
    """Simple console driven controller for local multiplayer hot-seat games."""

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._event_bus: EventBusLike | None = None
        self._input = input_fn or input
        self._output = output_fn or print
        self._pending_actor: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API expected by the InputController protocol
    # ------------------------------------------------------------------
    def bind(self, event_bus: EventBusLike) -> None:
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
    def _handle_request_actions(self, *, actor_id: str, **_: Any) -> None:
        actor_id = str(actor_id)
        self._pending_actor = actor_id
        self.on_request_actions(actor_id)

    def _handle_actions_available(
        self,
        *,
        actor_id: str,
        actions: Iterable[Mapping[str, Any]] | None = None,
        source_player_id: Optional[str] = None,
        client_tx_id: Optional[str] = None,
        **_: Any,
    ) -> None:
        if not self._event_bus:
            return

        actor_id = str(actor_id)
        if self._pending_actor is not None and actor_id != self._pending_actor:
            return

        actions_list = list(actions or [])
        if not actions_list:
            self._output("[HotSeat] No actions available.")
            return

        self._output(f"[HotSeat] Available actions for {actor_id}:")
        for idx, action in enumerate(actions_list, start=1):
            label = action.get("name") or action.get("id") or f"Action {idx}"
            self._output(f"  {idx}. {label}")

        choice = self._prompt_index(
            len(actions_list), prompt="Select action (or 0 to skip): "
        )
        if choice <= 0:
            self._output("[HotSeat] Action selection skipped.")
            return

        action_data = actions_list[choice - 1]
        targets = self._prompt_targets(action_data)
        params = dict(action_data.get("default_params", {}))

        intent = ActionIntent(
            actor_id=actor_id,
            action_id=str(action_data.get("id") or action_data.get("name")),
            targets=tuple(targets),
            params=params,
            source_player_id=source_player_id,
            client_tx_id=client_tx_id,
        )

        self._publish(topics.INTENT_SUBMITTED, {"intent": intent.to_dict()})

    def _handle_reaction_window(
        self, *, actor_id: str, options: Iterable[Mapping[str, Any]] | None = None, **_: Any
    ) -> None:
        if not self._event_bus:
            return

        actor_id = str(actor_id)
        options_list = list(options or [])
        context = {"options": options_list}
        self.on_reaction_prompt(context)

        if not options_list:
            self._publish(
                topics.REACTION_DECLARED,
                {"actor_id": actor_id, "reaction": None, "passed": True},
            )
            return

        choice = self._prompt_index(
            len(options_list), prompt="Select reaction (0 to pass): "
        )
        if choice <= 0:
            payload = {"actor_id": actor_id, "reaction": None, "passed": True}
        else:
            payload = {
                "actor_id": actor_id,
                "reaction": options_list[choice - 1],
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
            raw_kind = descriptor.get("kind") or descriptor.get("type") or ""
            kind = raw_kind.lower()
            if kind == "self":
                targets.append(TargetSpec.self())
                continue

            label = raw_kind or kind or "target"
            prompt = descriptor.get("prompt") or f"Provide target for {label}: "
            while True:
                user_input = self._input(prompt).strip()
                if not user_input:
                    break

                try:
                    target = self._build_target(kind, raw_kind, user_input, descriptor)
                except ValueError as error:
                    self._output(str(error))
                    continue

                targets.append(target)
                break

        return targets

    def _build_target(
        self, kind: str, raw_kind: str, user_input: str, descriptor: Mapping[str, Any]
    ) -> TargetSpec:
        if kind == "entity":
            return TargetSpec.entity(user_input)
        if kind == "tile":
            coords = self._parse_coordinates(user_input)
            return TargetSpec.tile(coords)
        if kind == "area":
            coords_part, _, radius_part = user_input.partition(";")
            coords = self._parse_coordinates(coords_part)
            default_radius = descriptor.get("radius", 0)
            shape = descriptor.get("shape", "circle")
            radius = self._parse_radius(radius_part, default_radius)
            return TargetSpec.area(coords, shape=shape, radius=radius)

        effective_kind = raw_kind or kind or "custom"
        return TargetSpec(kind=str(effective_kind), extra={"value": user_input})

    def _parse_coordinates(self, raw_value: str) -> tuple[int, ...]:
        parts = [part.strip() for part in raw_value.split(",") if part.strip()]
        if not parts:
            raise ValueError(
                "Invalid coordinates. Please enter comma-separated integers (e.g., 3,4)."
            )
        try:
            return tuple(int(part) for part in parts)
        except ValueError as exc:  # pragma: no cover - exercised via CLI flows
            raise ValueError(
                "Invalid coordinates. Please enter comma-separated integers (e.g., 3,4)."
            ) from exc

    def _parse_radius(self, raw_value: str, default: int | float | str | None) -> int:
        candidate = raw_value.strip()
        if not candidate:
            try:
                return int(default)
            except (TypeError, ValueError) as exc:  # pragma: no cover - config issue
                raise ValueError("Invalid default radius configured for target descriptor.") from exc
        try:
            return int(candidate)
        except ValueError as exc:  # pragma: no cover - exercised via CLI flows
            raise ValueError(
                "Invalid radius. Please enter an integer value (e.g., 3,4;2)."
            ) from exc

    def _publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        if not self._event_bus:
            raise RuntimeError("Controller must be bound to an event bus before use.")
        self._event_bus.publish(topic, **payload)


__all__ = ["HotSeatCLIController"]

