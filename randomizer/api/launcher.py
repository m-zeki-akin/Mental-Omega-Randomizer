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
    from randomizer.campaign import store

    state = store.standing()
    if not state.get('seed'):
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
    standing = screen_table.family(current)
    return {
        'current': current,
        'label': screen_table.label(current),
        'family': standing,
        # Two levels, because five modes are two kinds of game: which kind
        # is being played, and which one of that kind. What is stored is
        # still one of the five.
        'families': [
            {
                'name': family['name'],
                'description': family['description'],
                'current': family['name'] == standing,
                'modes': [
                    {
                        'name': entry['mode'],
                        'label': entry['label'],
                        'ported': entry['mode'] in screen_table.PORTED,
                        'current': entry['mode'] == current,
                    }
                    for entry in family['modes']
                ],
            }
            for family in screen_table.families()
        ],
        'modes': [
            {
                'name': mode,
                'label': screen_table.label(mode),
                'family': screen_table.family(mode),
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
    """Take either a mode or the kind of game one belongs to.

    The control is two, so this answers to both: a kind of game means the
    first of that kind unless what is being played is already one of them,
    and a mode means that mode. One action rather than two, because it is
    one decision -- what the launcher is set to play.
    """
    wanted = str(name or '').strip()
    config = _settings()
    current = screen_table.known(config.get(MODE_KEY))
    if wanted not in screen_table.BY_MODE:
        within = screen_table.modes_in(wanted)
        if not within:
            raise ApiError(f'There is no {wanted or "unnamed"} mode')
        wanted = current if current in within else within[0]
    if session.running():
        raise ApiError('Wait for the running game to close')
    if current != wanted:
        config[MODE_KEY] = wanted
        _keep(config)
    return {
        'current': wanted,
        'label': screen_table.label(wanted),
        'family': screen_table.family(wanted),
        'ported': wanted in screen_table.PORTED,
        'screens': [
            {'name': screen, 'label': label}
            for screen, label in screen_table.screens(wanted)
        ],
    }


# What a mission is written out looking and sounding like. Three
# settings that belong to no mode -- they are the same in a campaign run
# and a Shop one -- and that the classic window keeps among its own, which
# is why they had no home here.
LOOK = 'player_color'
SHUFFLE = 'rainbowizer'
VOICE = 'eva_voice'


def _mission_look(config):
    """Return the three, each with what it may be."""
    from randomizer.rewards.display import valid_choice
    from randomizer.ui.config import EVA_VOICE_CHOICES, PLAYER_COLORS

    return {
        LOOK: {
            'value': valid_choice(
                config.get(LOOK), PLAYER_COLORS, PLAYER_COLORS[0],
            ),
            'choices': list(PLAYER_COLORS),
        },
        SHUFFLE: {'value': bool(config.get(SHUFFLE, False))},
        VOICE: {
            'value': valid_choice(
                config.get(VOICE), EVA_VOICE_CHOICES, EVA_VOICE_CHOICES[0],
            ),
            'choices': list(EVA_VOICE_CHOICES),
        },
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
        'mission': _mission_look(config),
    }


@action(
    'launcher.use_mission_look',
    'Change how a mission is written out looking and sounding',
    kind=COMMAND,
)
def use_mission_look(name='', value=None):
    """Keep one of the three, and answer with all of them.

    They are read where a mission is written rather than where a run is
    generated, which is why they sit here and not on a mode's setup: two
    runs made from the same seed play the same however these are set.
    """
    wanted = str(name or '').strip()
    if wanted not in (LOOK, SHUFFLE, VOICE):
        raise ApiError(f'There is no {wanted or "unnamed"} appearance setting')
    config = _settings()
    if wanted == SHUFFLE:
        if not isinstance(value, bool):
            raise ApiError('Whether the houses are shuffled is yes or no')
        config[SHUFFLE] = value
    else:
        offered = _mission_look(config)[wanted]['choices']
        chosen = str(value or '')
        if chosen not in offered:
            raise ApiError(f'{chosen or "That"} is not one of the choices')
        config[wanted] = chosen
    _keep(config)
    return appearance()


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
