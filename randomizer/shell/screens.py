"""Which screens a mode has, and in what order.

The launcher is five modes, and which one is being played decides what
there is to look at. That used to be a dropdown among the settings of one
of them; it belongs above everything, because everything below it changes.

One table, here, rather than a list of tabs written into the page. The page
asks what the mode has and draws that, so a mode gains a screen by gaining
a row here and nothing else needs to know.

A mode whose screens are not drawn yet says so on a screen of its own. That
is not a placeholder for its own sake: a launcher that offers a mode and
then shows an empty panel is worse than one that says where the mode is.
"""

from randomizer.ui.config import (
    DEFAULT_PROGRESSION_MODE,
    PROGRESSION_MODES,
)


# The screen that belongs to no mode because it is about the launcher
# rather than about a run. It is last, and it is on every mode.
LAUNCHER_SCREEN = ('launcher', 'Launcher')
# What each mode is drawn as. A pair is the view's own name -- which is
# both its file and the id of the panel it draws into -- and the word on
# its tab.
BY_MODE = {
    'Classic': (('classic', 'Campaign'),),
    'Mission List': (('classic', 'Campaign'),),
    'Grid Mode': (('classic', 'Campaign'),),
    'Shop Mode': (('classic', 'Shop'),),
    'Skirmish Shop': (
        ('skirmish', 'Battle'),
        ('setup', 'Setup'),
        ('records', 'Records'),
    ),
}
# The modes drawn here rather than in the classic window. Read from the
# table rather than listed again: a mode is ported when its screens are.
PORTED = frozenset(
    mode for mode, screens in BY_MODE.items()
    if not all(name == 'classic' for name, _label in screens)
)


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
