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
    (0, 'Teal', (0, 168, 168)), (1, 'Red', (255, 0, 0)),
    (2, 'Aqua', (0, 255, 255)), (3, 'Lime', (1, 255, 0)),
    (4, 'Purple', (180, 91, 229)), (5, 'Yellow', (255, 216, 0)),
    (6, 'Blue', (0, 150, 255)), (7, 'Orange', (255, 132, 0)),
    (8, 'Magenta', (223, 0, 255)), (9, 'Brown', (178, 103, 50)),
    (10, 'Green', (119, 190, 38)), (11, 'Crimson', (178, 0, 66)),
    (12, 'Sky', (145, 180, 255)),
)
# What a colour is worth being told apart from, when the table cannot say.
# Mid grey: every colour is the same distance from it, so a palette that
# could not be read spreads the way it always did rather than clustering
# every house on one entry.
UNKNOWN_RGB = (128, 128, 128)


@lru_cache(maxsize=1)
def color_table():
    """Return ``((id, name, (r, g, b)), ...)``, in the client's order.

    The red, green and blue are read as well as the number, because who
    wears what is decided by which colours look alike: the ally wears the
    one nearest the player's and the enemies wear the ones furthest from
    both.
    """
    section = read_ini_sections(GAME_OPTIONS_PATH).get(MP_COLORS) or {}
    found = []
    for name, value in section.items():
        parts = [item.strip() for item in str(value).split(',')]
        if len(parts) < 4 or not parts[3].lstrip('-').isdigit():
            continue
        channels = tuple(
            int(part) if part.lstrip('-').isdigit() else 0
            for part in parts[:3]
        )
        found.append((int(parts[3]), str(name), channels))
    if not found:
        log_event('skirmish_colors_unreadable', path=str(GAME_OPTIONS_PATH))
        return STOCK_COLORS
    return tuple(found)


def player_colors():
    """Return ``((id, name), ...)`` for every colour, in the client's order."""
    return tuple((number, name) for number, name, _rgb in color_table())


def color_rgb(number):
    """Return one colour's red, green and blue."""
    for found, _name, channels in color_table():
        if found == number:
            return channels
    return UNKNOWN_RGB


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


def apart(one, other):
    """How far two colours are from each other, to the eye."""
    first, second = color_rgb(one), color_rgb(other)
    return sum(
        (int(a) - int(b)) ** 2 for a, b in zip(first, second)
    ) ** 0.5


def house_colors(*, player, taken=(), friends=0, foes=0):
    """Return one colour per computer player: allies first, then enemies.

    Who is on the player's side should be readable off the minimap without
    counting. So the ally wears the colour nearest the player's own -- blue
    and cyan -- and the enemies wear the ones furthest from both, which on
    the stock palette lands them in the reds and oranges.

    Enemies are picked one at a time, each the furthest from everything
    already worn rather than from the player alone. Furthest from the
    player alone would seat crimson beside red: both are far from blue and
    neither is far from the other.
    """
    spare = [
        number for number in color_ids()
        if number != player and number not in set(taken)
    ]
    many = int(friends) + int(foes)
    if not spare:
        # Nothing to hand out. Wearing the player's colour is wrong, but a
        # house has to wear something and the alternative is no launch.
        return tuple(player for _ in range(many))

    def furthest_from(avoid, among):
        return max(among, key=lambda one: (
            min(apart(one, other) for other in avoid), -one,
        ))

    worn = [player]
    allies = []
    for _ in range(int(friends)):
        left = [one for one in spare if one not in allies]
        if not left:
            break
        # Nearest the player, not nearest everything worn: an ally reads as
        # the player's side by looking like the player.
        allies.append(min(left, key=lambda one: (apart(one, player), one)))
    worn.extend(allies)

    enemies = []
    for _ in range(int(foes)):
        left = [one for one in spare if one not in allies + enemies]
        if not left:
            break
        enemies.append(furthest_from(worn + enemies, left))

    picked = allies + enemies
    # A palette smaller than the line-up repeats rather than refusing.
    while len(picked) < many:
        picked.append(spare[len(picked) % len(spare)])
    return tuple(picked)
