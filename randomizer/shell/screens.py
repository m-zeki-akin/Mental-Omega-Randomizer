"""Which screens a mode has, and in what order.

The launcher is five modes, and which one is being played decides what
there is to look at. That used to be a dropdown among the settings of one
of them; it belongs above everything, because everything below it changes.

The five are two kinds of game, and offering them flat made a player read
a list rather than make a choice. So the control is two: which kind --
the campaign, or a roguelike run -- and then which one of that kind. The
grouping is in configs/ui.json beside the modes themselves; what a
workspace stores is still one of the five.

One table, here, rather than a list of tabs written into the page. The page
asks what the mode has and draws that, so a mode gains a screen by gaining
a row here and nothing else needs to know.

A mode whose screens are not drawn yet says so on a screen of its own. That
is not a placeholder for its own sake: a launcher that offers a mode and
then shows an empty panel is worse than one that says where the mode is.
"""

from randomizer.ui.config import (
    DEFAULT_PROGRESSION_MODE,
    MODE_FAMILIES,
    PROGRESSION_MODES,
    mode_family,
    mode_label,
    modes_in_family,
)


# The screen that belongs to no mode because it is about the launcher
# rather than about a run. It is last, and it is on every mode.
LAUNCHER_SCREEN = ('launcher', 'Launcher')
# What each mode is drawn as. A pair is the view's own name -- which is
# both its file and the id of the panel it draws into -- and the word on
# its tab.
BY_MODE = {
    # 'Mode' rather than 'Campaign' on the tab: the kind of game is named
    # in the control above it now, and a tab repeating it says nothing.
    'Classic': (('classic', 'Mode'),),
    'Mission List': (('classic', 'Mode'),),
    'Grid Mode': (('classic', 'Mode'),),
    # Its setup is here and its run is not: what a run is started with
    # outlives the run, and both windows read it from one place. The
    # mode's own panel says where the run itself is played.
    'Shop Mode': (
        ('shop', 'Setup'),
        ('classic', 'Mode'),
    ),
    'Skirmish Shop': (
        ('skirmish', 'Battle'),
        ('setup', 'Setup'),
        ('records', 'Records'),
    ),
}
# The modes that are *played* here, which is not the same as the modes
# that have a screen here. Shop Mode's setup is drawn and its run is not,
# and a mode control that called that ported would be telling a player
# they can play it in this window.
PORTED = frozenset({'Skirmish Shop'})


def families():
    """Return the kinds of game, each with the modes that are one of it."""
    return [
        {
            'name': family['name'],
            'description': family['description'],
            'modes': [
                {'mode': entry['mode'], 'label': entry['label']}
                for entry in family['modes'] if entry['mode'] in BY_MODE
            ],
        }
        for family in MODE_FAMILIES
    ]


def family(mode):
    """Return the name of the kind of game a mode is, or the first kind."""
    return mode_family(known(mode))


def label(mode):
    """Return what a mode is called inside its own kind of game."""
    return mode_label(known(mode))


def modes_in(name):
    """Return the modes of one kind of game that this interface can draw."""
    return [mode for mode in modes_in_family(name) if mode in BY_MODE]


def known(mode):
    """Return the mode as the launcher names it, or its default."""
    wanted = str(mode or '').strip()
    if wanted in BY_MODE:
        return wanted
    return (
        DEFAULT_PROGRESSION_MODE if DEFAULT_PROGRESSION_MODE in BY_MODE
        else PROGRESSION_MODES[0]
    )


def screens(mode):
    """Return the screens one mode is drawn as, launcher last."""
    return BY_MODE.get(known(mode), ()) + (LAUNCHER_SCREEN,)


def view_names():
    """Return every view the table can ask for."""
    named = {LAUNCHER_SCREEN[0]}
    for pairs in BY_MODE.values():
        named.update(name for name, _label in pairs)
    return sorted(named)


def modes():
    """Return every mode, in the order the launcher lists them."""
    return [mode for mode in PROGRESSION_MODES if mode in BY_MODE]
