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
from .maps import (
    SkirmishMap,
    challenge_map_pool,
    maps_for_players,
    skirmish_map_pool,
)
from .spawn import (
    SkirmishHouse,
    skirmish_spawn_ini_text,
)


__all__ = (
    'SKIRMISH_SIDES',
    'SkirmishCountry',
    'SkirmishHouse',
    'SkirmishMap',
    'challenge_map_pool',
    'maps_for_players',
    'skirmish_countries',
    'skirmish_map_pool',
    'skirmish_spawn_ini_text',
    'validate_installed_countries',
)
