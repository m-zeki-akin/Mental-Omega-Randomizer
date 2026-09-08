"""The colours a house may wear, read from the rules the game loads.

``[Colors]`` in ``rulesmo.ini`` is what names a colour for the engine: a map
house wearing ``Color=Gold`` gets whatever that section says Gold is, and a
submod is free to say something else, to rename an entry, or to add ones the
stock game never had.

The list used to be a copy of those names committed to ``ui.json``, which
made every edit to the rules invisible to the launcher. On this installation
that copy offered 23 of the 43 colours the rules define and left out thirteen
the player could legitimately wear -- LightGrey, NeonBlue, Khaki, LightGold,
BrightGrey, Grey, DarkSky, Black, Thistle, Xanadu, Jade, Charcoal and Peri --
while changes to the ones it did offer never reached the interface at all.

So the names come from the installation now, through the same registry the
shop prices units from, which resolves the chain the engine resolves: a loose
``rulesmo.ini`` in the game folder outranks the archives, and among the
archives the highest-numbered ``expandmo`` wins. ``ui.json`` keeps the list
as the answer for an installation that cannot be read -- a development run
with no game beside it, or a first launch before the rules cache is built.

Nothing here picks a colour. It says which ones exist to be picked.
"""

from randomizer.core.diagnostics import event as log_event

from .config import (
    NON_HOUSE_COLOR_SUFFIXES,
    PLAYER_COLORS,
    RAINBOWIZER_COLORS,
)


RULES_COLORS_SECTION = 'Colors'
# What the player picks to mean "leave the map's own colour alone". It is not
# a colour in the rules and must stay first, because it is also the fallback
# a stored choice lands on when it names a colour this installation lost.
DEFAULT_CHOICE = 'Default'


def _is_house_color(name):
    """Whether a ``[Colors]`` entry is one a house can actually wear.

    The section carries more than player colours. Mental Omega keeps the
    message colours (``FirstText``..``FourthText``) and the loading-screen
    colours (``AlliedLoad``, ``SovietLoad``, ``ThirdLoad``) in it too, and
    offering those would let a player dress an army in a colour meant for
    subtitles. They are told apart by their suffix rather than by a list of
    the names themselves, so a submod that adds a fifth message colour does
    not have to be known about here to be excluded.
    """
    text = str(name or '').strip()
    if not text:
        return False
    return not any(
        text.lower().endswith(suffix.lower())
        for suffix in NON_HOUSE_COLOR_SUFFIXES
    )


# The names last read, and nothing more clever than that. The registry this
# reads through already caches, and already notices an installation that
# changed underneath it -- but it hands back a fresh copy of all ~4,700
# sections on every call, which is too much work to repeat each time a
# dropdown is built. So the palette is kept here and dropped the moment the
# registry says the installation moved.
#
# It must be dropped on that signal rather than held for the process: the
# workflow this exists for is edit rulesmo, repack the mix, look at the
# launcher again. A palette pinned for the lifetime of the process would be
# right exactly once and stale for every repack after it, which is the bug
# this module was written to fix, one layer up.
_NAMES = None


def rules_color_names():
    """Return every wearable ``[Colors]`` name, in the rules' own order.

    Order is the file's, not sorted: the rules list the multiplayer colours
    first and the spare ones after, so keeping it puts the colours a player
    expects at the top of the dropdown.

    Returns an empty tuple when the installation cannot be read, which the
    callers below turn into the committed list rather than an empty dropdown.
    """
    global _NAMES
    try:
        from randomizer.ui.cameos import (
            ensure_current_installed_cache,
            installed_rules_registry,
        )
        # True means the archives or the loose override changed, so whatever
        # was read before this describes an installation that is gone.
        if ensure_current_installed_cache():
            _NAMES = None
        if _NAMES is not None:
            return _NAMES
        _superweapons, sections = installed_rules_registry(synchronous=True)
    except Exception as error:
        # An installation that cannot be read is not an error worth stopping
        # a launch over - the committed list still names real colours.
        log_event('rules_colors_unreadable', error=str(error))
        return ()
    for section, values in (sections or {}).items():
        if str(section).strip().lower() != RULES_COLORS_SECTION.lower():
            continue
        _NAMES = tuple(
            str(name).strip()
            for name in (values or {})
            if _is_house_color(name)
        )
        return _NAMES
    log_event('rules_colors_absent')
    return ()


def player_color_choices():
    """Return what the player may set their own houses to."""
    found = rules_color_names()
    if not found:
        return tuple(PLAYER_COLORS)
    return (DEFAULT_CHOICE, *found)


def rainbowizer_color_choices():
    """Return the colours the rainbowizer may hand to computer players."""
    found = rules_color_names()
    if not found:
        return tuple(RAINBOWIZER_COLORS)
    return found


def forget_rules_colors():
    """Drop the kept palette. Normally unnecessary -- ``rules_color_names``
    drops it by itself when the registry reports the installation changed --
    and here for a caller that knows it changed something the signature does
    not cover."""
    global _NAMES
    _NAMES = None
