"""The colours a skirmish is played in.

The client keeps them in ``Resources/GameOptions.ini`` under ``[MPColors]``,
one line per colour: a name, its red, green and blue, and last the number
the spawn file calls it by. That last number is what goes into ``Color=``
and ``[HouseColors]``, so the list is read rather than assumed -- a submod
that reorders or renames its colours is still answered correctly, and one
that ships fewer of them does not get houses wearing a colour that is not
there.

Nothing here picks. It says what may be picked from, and ``launch`` decides
who wears what once the map has had its say: a challenge map names colours
its own armies wear, and the player is kept out of those.
"""

from functools import lru_cache

from randomizer.core.diagnostics import event as log_event

from .options import GAME_OPTIONS_PATH, read_ini_sections


MP_COLORS = 'MPColors'
# What the run stores when nobody has chosen: the launcher picks, which is
# what it did before there was anything to choose.
UNCHOSEN = -1
# The stock thirteen, in the client's own order, for an installation whose
# GameOptions.ini cannot be read. A launch has to be able to name a colour.
STOCK_COLORS = (
    (0, 'Teal'), (1, 'Red'), (2, 'Aqua'), (3, 'Lime'), (4, 'Purple'),
    (5, 'Yellow'), (6, 'Blue'), (7, 'Orange'), (8, 'Magenta'), (9, 'Brown'),
    (10, 'Green'), (11, 'Crimson'), (12, 'Sky'),
)


@lru_cache(maxsize=1)
def player_colors():
    """Return ``((id, name), ...)`` for every colour, in the client's order."""
    section = read_ini_sections(GAME_OPTIONS_PATH).get(MP_COLORS) or {}
    found = []
    for name, value in section.items():
        parts = [item.strip() for item in str(value).split(',')]
        if len(parts) < 4 or not parts[3].lstrip('-').isdigit():
            continue
        found.append((int(parts[3]), str(name)))
    if not found:
        log_event('skirmish_colors_unreadable', path=str(GAME_OPTIONS_PATH))
        return STOCK_COLORS
    return tuple(found)


def color_ids():
    """Return every colour number, in the client's order."""
    return tuple(number for number, _name in player_colors())


def color_name(number):
    """Return what the client calls one colour, or its number."""
    for found, name in player_colors():
        if found == number:
            return name
    return str(number)


def is_a_color(number):
    """Whether this installation has a colour by that number."""
    return int(number) in set(color_ids())


def house_colors(*, player, taken=(), many=0):
    """Return one colour per computer player, none of them the player's.

    Spread through the list rather than taken from the front, because
    neighbouring entries are neighbouring colours and two armies a player
    has to tell apart at a glance should not both be blue.
    """
    spare = [
        number for number in color_ids()
        if number != player and number not in set(taken)
    ]
    if not spare:
        return tuple(player for _ in range(many))
    step = max(1, len(spare) // max(1, many))
    picked = [spare[(index * step) % len(spare)] for index in range(many)]
    # A short list can repeat; a long enough one never should.
    seen = []
    for number in picked:
        if number in seen and len(seen) < len(spare):
            number = next(one for one in spare if one not in seen)
        seen.append(number)
    return tuple(seen)
