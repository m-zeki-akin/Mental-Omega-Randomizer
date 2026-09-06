"""What the launcher is, rather than what a run is.

One screen's worth so far: which of the two interfaces opens at a start.
The new one draws a mode and a half, so a player who wants the rest has to
be able to go back without a command line -- and a player who likes it has
to be able to stay without one either.
"""

from randomizer.shell.choice import CLASSIC, NEW, remember, remembered

from .contract import COMMAND, ApiError, action


@action('launcher.interface', 'Which interface opens when the launcher starts')
def interface():
    from randomizer.config.player import load_config

    kept = remembered(load_config())
    return {
        'interface': kept,
        'new': kept == NEW,
        'classic_label': 'Classic window',
        'new_label': 'New interface',
    }


@action(
    'launcher.use_interface',
    'Keep one of the two interfaces as the one that opens',
    kind=COMMAND,
)
def use_interface(name=''):
    """Remember which interface opens next time.

    Next time and not this one: a window cannot become another one while
    it is open, and pretending otherwise would mean closing the launcher
    under somebody who only meant to change a setting.
    """
    wanted = str(name or '').strip().lower()
    if wanted not in (CLASSIC, NEW):
        raise ApiError(f'There is no {wanted or "unnamed"} interface')
    kept = remember(wanted)
    return {
        'interface': kept,
        'message': (
            'The classic window opens the next time the launcher starts.'
            if kept == CLASSIC else
            'This interface opens the next time the launcher starts.'
        ),
    }
