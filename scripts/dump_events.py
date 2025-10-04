#!/usr/bin/env python3
"""Diagnostics utility that prints every combat system event passing on the bus."""

from __future__ import annotations

import argparse
import datetime as _dt
import pprint
import time
from typing import Callable, Iterable, Sequence

from core.event_bus import EventBus
from core.events import topics as topic_constants


def _collect_topic_names(candidates: Iterable[str | tuple[str, str]] | None = None) -> list[str]:
    if candidates is None:
        symbols = {
            value
            for name, value in vars(topic_constants).items()
            if name.isupper() and isinstance(value, str)
        }
        return sorted(symbols)

    names: set[str] = set()
    for entry in candidates:
        if isinstance(entry, tuple):
            names.add(str(entry[1]))
        else:
            names.add(str(entry))
    return sorted(names)


class EventLogger:
    """Subscriber that prints event payloads as they go through the bus."""

    def __init__(
        self,
        *,
        printer: Callable[[str], None] | None = None,
        include_timestamp: bool = True,
        pretty: bool = True,
    ) -> None:
        self._printer = printer or print
        self._include_timestamp = include_timestamp
        self._formatter = pprint.PrettyPrinter(indent=2) if pretty else None

    def __call__(self, topic: str, **payload: object) -> None:
        timestamp = ""
        if self._include_timestamp:
            timestamp = _dt.datetime.now().strftime("[%H:%M:%S] ")
        header = f"{timestamp}{topic}"
        if self._formatter:
            body = self._formatter.pformat(payload)
        else:
            body = str(payload)
        self._printer(f"{header}\n{body}\n")


def attach_to_bus(
    bus: EventBus,
    *,
    topics: Sequence[str] | None = None,
    include_timestamp: bool = True,
    pretty: bool = True,
    printer: Callable[[str], None] | None = None,
) -> EventLogger:
    """Subscribe an :class:`EventLogger` to ``bus`` for the provided topics."""

    topic_list = _collect_topic_names(topics)
    logger = EventLogger(printer=printer, include_timestamp=include_timestamp, pretty=pretty)

    def _make_handler(name: str) -> Callable[..., None]:
        def _handler(**payload: object) -> None:
            logger(name, **payload)

        return _handler

    for topic in topic_list:
        bus.subscribe(topic, _make_handler(topic))
    return logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump combat system events for diagnostics.")
    parser.add_argument(
        "--topics",
        metavar="TOPICS",
        help="Comma-separated list of topic names to monitor (default: all known topics).",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Disable pretty-printing of payloads (raw dict repr).",
    )
    parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="Do not prefix events with the current time.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Emit a demo event after wiring the logger to illustrate the output format.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    topics = None
    if args.topics:
        topics = [entry.strip() for entry in args.topics.split(",") if entry.strip()]

    bus = EventBus()
    attach_to_bus(
        bus,
        topics=topics,
        include_timestamp=not args.no_timestamp,
        pretty=not args.plain,
    )

    print("Event logger ready.")
    print("Import 'attach_to_bus' from scripts.dump_events to monitor a running bus instance.")
    print("Press Ctrl+C to exit.")

    if args.demo:
        bus.publish(topic_constants.REQUEST_ACTIONS, actor_id="demo_actor", reason="demo")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping event logger.")


if __name__ == "__main__":
    main()
