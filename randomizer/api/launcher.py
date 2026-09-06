"""What the launcher is, rather than what a run is.

Two things live here because they are true whichever mode is being played:
which mode that is, and how the launcher itself is set up. Everything a
mode decides for itself belongs with that mode's own screens -- a setting
put where it cannot be seen from the thing it changes is a setting nobody
finds twice.
"""

from randomizer.shell import screens as screen_table
from randomizer.shell.choice import CLASSIC, NEW, remember, remembered

from . import session
from .contract import COMMAND, ApiError, action


MODE_KEY = 'progression_mode'
THEME_KEY = 'dark_mode'
DARK = 'dark'
LIGHT = 'light'


def _settings():
    from randomizer.config.player import load_config

    return load_config()


def _keep(config):
    from randomizer.config.player import save_config

    save_config(config)


def _campaign_seed():
    """Return the seed the classic window generated, and what for.

    A campaign mode's own progression is fixed when its seed is made, so a
    seed already standing is worth saying: it is why the classic window
    will open on that mode whatever this one is set to.
    """
    from randomizer.core.paths import STATE_PATH
    from randomizer.core.storage import read_json_object

    try:
        if not STATE_PATH.is_file():
            return {}
        state = read_json_object(STATE_PATH)
    except (OSError, ValueError):
        return {}
    if not isinstance(state, dict) or not state.get('seed'):
        return {}
    return {
        'seed': str(state.get('seed') or ''),
        'mode': str(state.get(MODE_KEY) or ''),
    }


@action('launcher.modes', 'Every mode, and which one is being looked at')
def modes():
    """The mode, its screens, and whether it may be changed right now.

    A screen draws what this says rather than deciding any of it, so a
    mode gains a tab by gaining a row in the table and nothing in the page
    has to be told.
    """
    current = screen_table.known(_settings().get(MODE_KEY))
    playing = session.running()
    return {
        'current': current,
        'modes': [
            {
                'name': mode,
                'ported': mode in screen_table.PORTED,
                'current': mode == current,
            }
            for mode in screen_table.modes()
        ],
        'screens': [
            {'name': name, 'label': label}
            for name, label in screen_table.screens(current)
        ],
        # Not while a battle this launcher started is up: the screens
        # would change under a game that is still being played.
        'locked': playing,
        'locked_by': 'A battle is being played' if playing else '',
        'campaign_seed': _campaign_seed(),
    }


@action('launcher.use_mode', 'Look at another mode', kind=COMMAND)
def use_mode(name=''):
    wanted = str(name or '').strip()
    if wanted not in screen_table.BY_MODE:
        raise ApiError(f'There is no {wanted or "unnamed"} mode')
    if session.running():
        raise ApiError('Wait for the running game to close')
    config = _settings()
    if screen_table.known(config.get(MODE_KEY)) != wanted:
        config[MODE_KEY] = wanted
        _keep(config)
    return {
        'current': wanted,
        'ported': wanted in screen_table.PORTED,
        'screens': [
            {'name': screen, 'label': label}
            for screen, label in screen_table.screens(wanted)
        ],
    }


@action('launcher.appearance', 'How the launcher itself is set up')
def appearance():
    config = _settings()
    kept = remembered(config)
    return {
        'interface': kept,
        'new': kept == NEW,
        'theme': DARK if config.get(THEME_KEY) else LIGHT,
        'dark': bool(config.get(THEME_KEY)),
    }


@action('launcher.use_theme', 'Draw the launcher light or dark', kind=COMMAND)
def use_theme(name=''):
    """Both interfaces read one setting, so both change together."""
    wanted = str(name or '').strip().lower()
    if wanted not in (DARK, LIGHT):
        raise ApiError(f'There is no {wanted or "unnamed"} theme')
    config = _settings()
    config[THEME_KEY] = wanted == DARK
    _keep(config)
    return {'theme': wanted, 'dark': wanted == DARK}


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
