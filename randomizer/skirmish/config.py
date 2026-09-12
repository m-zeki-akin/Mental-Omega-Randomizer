"""The Skirmish Shop's balance, read from ``configs/skirmish.json``.

Everything a run is tuned by lives in that file: what a battle pays, what
an upgrade costs, how many enemies each tier fields and how well they play,
and what an offer may ask for. The modules below keep their own names for
those numbers -- ``SHELF_SIZE``, ``TIERS``, ``MODIFIERS`` -- and fill them
from here at import, so a rebalance is an edit to one JSON file and a
restart rather than a change to Python.

Only the numbers moved. What stays in code is structure: that the warmup is
battle zero, that a clone is prefixed ``MOP``, that a superweapon is not a
TechnoType. Those are not settings, and a file that invited someone to
change them would be inviting a launcher that does not work.

Difficulties are written the way a player says them -- easy, medium, hard
-- rather than as the engine's own numbering, which counts the other way
round and has misled everyone who has ever read it.
"""

from dataclasses import dataclass

from randomizer.config.static import load_static_config

from .spawn import (
    AI_DIFFICULTY_EASY,
    AI_DIFFICULTY_HARD,
    AI_DIFFICULTY_MEDIUM,
)


CONFIG_NAME = 'skirmish.json'

# What the file calls a difficulty, and what the spawn file calls it. The
# engine counts down: nought is Hard.
DIFFICULTY_NUMBERS = {
    'hard': AI_DIFFICULTY_HARD,
    'medium': AI_DIFFICULTY_MEDIUM,
    'easy': AI_DIFFICULTY_EASY,
}


def difficulty_number(name):
    """Return the spawn file's number for a difficulty written by name."""
    return DIFFICULTY_NUMBERS[str(name or '').strip().lower()]


@dataclass(frozen=True)
class TierSettings:
    """One rung of the ladder, still named rather than numbered."""

    enemies: tuple[int, ...]
    challenge: int
    mental: bool
    challenge_mental: bool
    enemy_upgrades: int


@dataclass(frozen=True)
class ModifierSettings:
    """One thing an offer may ask for, and what it pays for asking."""

    key: str
    label: str
    percent: int
    from_tier: int
    extra_enemies: int
    alone: bool
    mental: bool
    enemy_upgrades: int
    faction_upgrades: int
    enemy_stolen: bool


@dataclass(frozen=True)
class SkirmishSettings:
    economy: dict
    shelf: dict
    prices: dict
    run: dict
    warmup: TierSettings
    tiers: tuple[TierSettings, ...]
    modifiers: tuple[ModifierSettings, ...]
    enemy: dict


def _tier(entry):
    return TierSettings(
        enemies=tuple(
            difficulty_number(one) for one in entry.get('enemies') or ()
        ),
        challenge=difficulty_number(entry.get('challenge')),
        mental=bool(entry.get('mental', False)),
        challenge_mental=bool(entry.get('challenge_mental', False)),
        enemy_upgrades=int(entry.get('enemy_upgrades', 0)),
    )


def _modifier(entry):
    return ModifierSettings(
        key=str(entry['key']),
        label=str(entry['label']),
        percent=int(entry['percent']),
        from_tier=int(entry.get('from_tier', 1)),
        extra_enemies=int(entry.get('extra_enemies', 0)),
        alone=bool(entry.get('alone', False)),
        mental=bool(entry.get('mental', False)),
        enemy_upgrades=int(entry.get('enemy_upgrades', 0)),
        faction_upgrades=int(entry.get('faction_upgrades', 0)),
        enemy_stolen=bool(entry.get('enemy_stolen', False)),
    )


def load_skirmish_settings():
    """Read the balance file into the shapes the mode's modules want."""
    sections = load_static_config(CONFIG_NAME)
    tiers = sections['tiers']
    return SkirmishSettings(
        economy=dict(sections['economy']),
        shelf=dict(sections['shelf']),
        prices=dict(sections['prices']),
        run=dict(sections['run']),
        warmup=_tier(tiers['warmup']),
        tiers=tuple(_tier(entry) for entry in tiers['ladder']),
        modifiers=tuple(_modifier(entry) for entry in sections['modifiers']),
        enemy=dict(sections['enemy']),
    )


SETTINGS = load_skirmish_settings()
