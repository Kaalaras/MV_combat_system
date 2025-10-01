# MV Combat System

Modernized Python combat / condition engine with support for:
- Multi-component weapon damage (severity + category, magic variants)
- Armor flat soak + resistance multipliers (immunity / vulnerability) with precedence
- Stackable and timed conditions (initiative / max health / damage in-out modifiers)
- Dynamic damage-based weakened states
- Disciplines, subtypes (Undead, Vampire, Ghost) with special damage processing

## Quick Start
```bash
# Run fast unit test suite (avoid tests.manual or long-running aggregation)
python -m pytest tests/unit -q
# Run the full automated test suite (integration + unit)
pytest
```
Note (Windows / DataSpell): avoid using shell command chaining with `&&` inside the IDE terminal.

## Deterministic Attack Tests Pattern
To keep production code free of test logic we use **test-only subclasses**:
1. Subclass `AttackAction` inside the test file (e.g. `_TestAttackAction`).
2. Override `get_available_defenses` to return `[]` so no random defense occurs.
3. Inject a stub dice roller with `roll_pool` returning a fixed dict.

This guarantees stable outcomes while leaving runtime code untouched.

## Armor Resistance Precedence
`Armor.modify_incoming` applies multipliers in this order:
1. Category (e.g. `fire`, `gas`)
2. Severity (`superficial`, `aggravated`)
3. `all` catch‑all

Resulting multiplier = product of all matched entries. After that, flat soak is applied if severity matches and weapon type is protected.

## Stackable Conditions
Stackable names (see `STACKABLE_NAMES` in `condition_system.py`):
```
InitiativeMod, MaxHealthMod, DamageOutMod, DamageInMod
```
Rules:
- First instance keeps its base name (e.g. `InitiativeMod`).
- Additional concurrent instances get suffixes: `InitiativeMod#1`, `InitiativeMod#2`, ...
- Each instance maintains its own duration and side-effects.
- Removal (expiry or manual) reverts only that instance’s delta.

### Example Flow
1. Add `InitiativeMod +3 (3 rounds)` and `InitiativeMod -1 (2 rounds)` -> net +2.
2. After one round both tick; add `InitiativeMod +5 (1 round)` -> net +7.
3. Next round the `-1` and `+5` expire simultaneously -> net reverts to +3.
4. Manual removal of the base +3 returns initiative to baseline.

## Overflow Damage Rule
Superficial overflow collapses the track: if superficial + aggravated > max health, health is set to full aggravated and superficial cleared (character dead / incapacitated depending on design).

## Running Focused Tests
```bash
# Single file
python -m pytest tests/unit/test_stackable_condition_expiry.py -q
# Single test
python -m pytest tests/unit/test_stackable_condition_expiry.py::TestStackableExpiry::test_initiative_interleaved -q
```

## Adding New Stackable Condition Tests
Checklist:
- Add conditions in mixed order (positive, negative, different durations).
- Advance rounds with `event_bus.publish('round_started', round_number=n, turn_order=[eid])`.
- Assert intermediate deltas after each phase.
- Manually remove one suffix early and verify others remain.

## Project Structure Highlights
```
entities/            # Characters, weapons, armor, effects
ecs/actions/         # Attack + defensive + discipline actions
ecs/systems/         # Condition, action, movement systems
utils/               # Damage type classification, helpers
tests/unit/          # Fast unit test suite (keep deterministic!)
```

## Contributing
- Keep production code free from test-specific branching.
- Prefer new targeted test modules for edge cases over inflating existing ones.
- Ensure new damage or condition types integrate with classification & stacking rules.

## License
Internal / proprietary (adjust this section as needed).

## Fortitude Aggravated Downgrade Rule
When a defender has Fortitude >= 2 and is struck by aggravated damage:
- The system uses the legacy margin formula for the aggravated component: base = damage_bonus + (net_successes - 1) instead of base = damage_bonus + net_successes.
- Armor flat soak is skipped (Fortitude represents pre-armor supernatural resilience) but the damage is downgraded from aggravated to superficial at application time.
- Returned damage (for logging / external effects) reports the raw pre-downgrade value so analytics or triggers expecting historical aggravated potential still function.
This hybrid approach preserves older balance expectations while keeping newer net-based scaling for all other damage types.

## Damage Modifier Clamping
Outgoing (DamageOutMod) and incoming (DamageInMod) condition-based adjustments can reduce a computed damage amount. After all category / severity / all modifiers are applied, any result < 0 is clamped to 0 to avoid negative healing / siphon side-effects. Dedicated tests ensure:
- Small base damage fully nullified by negative modifiers.
- Multiple stacked negatives cannot drive damage below zero.
- Removal / expiry restores original damage potential.
