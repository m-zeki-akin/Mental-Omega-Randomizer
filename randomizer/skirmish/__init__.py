"""Skirmish Shop mode: the map pool, the line-up, and the spawn file.

Campaign missions and skirmish battles are launched by the same engine but
described to it in different terms. A mission is a scenario the game already
knows; a skirmish is a map plus a table of houses, and the file that says so
is written by the client rather than shipped with the game.

What lives here is the part of that with no user interface: which maps the
installation has, which countries it will index, and the exact spawn file
that starts a match. It is the shape a working launch was proven to need --
see ``spawn`` for what each rule cost to learn.
"""

from .factions import (
    SKIRMISH_SIDES,
    SkirmishCountry,
    skirmish_countries,
    validate_installed_countries,
)
from .model import (
    BattleOffer,
    SkirmishRun,
    SkirmishRunCollection,
)
from .maps import (
    SkirmishMap,
    challenge_map_pool,
    maps_for_players,
    skirmish_map_pool,
)
from .persistence import (
    SkirmishPersistenceError,
    SkirmishRepository,
)
from .progression import is_challenge_battle, offers_for, tier_for
from .results import last_game_result
from .spawn import (
    SkirmishHouse,
    skirmish_spawn_ini_text,
)


__all__ = (
    'SKIRMISH_SIDES',
    'BattleOffer',
    'SkirmishPersistenceError',
    'SkirmishRepository',
    'SkirmishRun',
    'SkirmishRunCollection',
    'SkirmishCountry',
    'SkirmishHouse',
    'SkirmishMap',
    'challenge_map_pool',
    'is_challenge_battle',
    'last_game_result',
    'offers_for',
    'maps_for_players',
    'skirmish_countries',
    'skirmish_map_pool',
    'skirmish_spawn_ini_text',
    'tier_for',
    'validate_installed_countries',
)
