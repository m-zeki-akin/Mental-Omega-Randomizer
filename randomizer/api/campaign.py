"""What a campaign run is set up with, before a seed is generated.

The three campaign modes share almost every setting -- they are the same
campaign in a different order -- so one screen answers for all three, and
the table says which of the rows belong to Grid alone.

Nothing here generates a seed or changes one that exists. A run that has
been generated keeps the settings it was generated with; these describe
the next one, which is why they are settings rather than run state. The
run itself is read, not written: ``campaign.run`` says how far the one
standing got, and the classic window is still where it is played.

How a table becomes a reply is not here either: that is the same question
for every setup screen, and it is answered once in ``settings``.
"""

from randomizer.campaign import progress, store
from randomizer.campaign.store import CHECK_SCHEMA_VERSION
from randomizer.ui import campaign_catalogues
from randomizer.ui.campaign_catalogues import CATALOGUE_NAMES
from randomizer.ui.campaign_settings import (
    ENEMY_CAPACITY,
    ENEMY_SCALING,
    SECTIONS,
)

from .contract import COMMAND, ApiError, action
from .settings import Settings


# What the stored run calls the mode it was generated for, and the one
# mode whose openings are a board rather than a count.
MODE_KEY = 'progression_mode'
GRID_MODE = 'Grid Mode'


def _enemy_capacity(config, row):
    """Return what the bonuses actually allowed could add up to.

    The enemy's total is capped by them: turning most of them off lowers
    what a run could ever hand out, and the generator has always clamped
    the number there. A screen going on offering the full range would be
    offering a number that is quietly cut on the way to the seed.

    With nothing allowed the number means nothing at all, and the help
    beside it says so. The row's own range is what is offered then: a
    stepper pinned dead at nought reads as a broken control, and the
    number it holds is not asked of anything until a bonus is allowed
    again.
    """
    from randomizer.rewards.enemy_scaling import enemy_buff_capacity

    held = config
    for step in ENEMY_SCALING.split('.'):
        inside = held.get(step)
        held = inside if isinstance(inside, dict) else {}
    capacity = enemy_buff_capacity(held)
    return min(row['maximum'], capacity) if capacity else row['maximum']


CAMPAIGN = Settings(
    SECTIONS,
    catalogues=campaign_catalogues,
    ceilings={ENEMY_CAPACITY: _enemy_capacity},
)
BY_KEY = CAMPAIGN.by_key


def _settings():
    from randomizer.config.player import load_config

    return load_config()


def _keep(config):
    from randomizer.config.player import save_config

    save_config(config)


def _standing():
    """Return the seed the classic window has generated, if one stands."""
    from .launcher import _campaign_seed

    return str((_campaign_seed() or {}).get('seed') or '')


def _mode(config):
    """Return the campaign mode being set up, if one is standing.

    Which is asked of the screen table rather than of the mode: the modes
    this screen answers for are exactly the modes it is a screen of, and
    that is one list, not two. Asked from a roguelike workspace it says
    nothing is standing, and what comes back is the settings the three
    campaign modes share, without any one mode's own.
    """
    from randomizer.shell import screens as screen_table

    current = screen_table.known(config.get('progression_mode'))
    drawn = [name for name, _label in screen_table.screens(current)]
    return current if 'campaign' in drawn else ''


def _answer(config):
    mode = _mode(config)
    # A seed already generated is a run in progress, and a run in progress
    # is why the seed box is empty in the classic window. Both windows say
    # the same thing about it, and this is what it is.
    standing = _standing()
    return {
        'mode': mode,
        'generated_seed': standing,
        'sections': CAMPAIGN.answer(config, mode=mode, blank=bool(standing)),
    }


def _missions_by_code():
    """Return every installed mission by its code, or nothing at all.

    Nothing at all is a real answer: a launcher opened away from the game
    still has a run written down, and a run whose missions are named by
    their codes is worth more than a screen that refuses to draw.
    """
    from randomizer.core.paths import BATTLE_CLIENT_INI
    from randomizer.missions.catalogue import (
        FALLBACK_OBJECTIVE_COUNT,
        parse_missions,
    )

    try:
        listed = parse_missions(BATTLE_CLIENT_INI, FALLBACK_OBJECTIVE_COUNT)
    except (OSError, ValueError):
        return {}
    return {str(entry['code']): entry for entry in listed}


def _mission_view(state, code, installed, tiles):
    """Return one mission of a run, as much as a screen needs of it."""
    entry = installed.get(code) or {}
    done, total = progress.check_counts(state, code)
    complete = progress.is_complete(state, code)
    if tiles:
        # Grid says so itself. A mission it has not opened is locked
        # however many have been won, which is the whole point of a board.
        open_now = tiles.get(code) in {'unlocked', 'completed'}
    else:
        open_now = code in _open_codes(state)
    return {
        'code': code,
        'name': str(entry.get('title') or code),
        'side': str(entry.get('side') or ''),
        'installed': bool(entry),
        'unlocked': bool(open_now),
        'started': progress.is_started(state, code),
        'complete': complete,
        'done': done,
        'total': total,
    }


def _open_codes(state):
    """Return the open missions once, rather than once per mission."""
    global _OPEN_FOR
    held = _OPEN_FOR
    if held is not None and held[0] is state:
        return held[1]
    codes = frozenset(progress.unlocked_codes(state))
    _OPEN_FOR = (state, codes)
    return codes


_OPEN_FOR = None


@action('campaign.run', 'The campaign run standing, or nothing')
def run():
    """Return how far the run written down has got.

    Read-only, and it says so: what a campaign mode is played in is still
    the classic window. What this answers is the question a player opens
    the launcher to ask -- which mission is next, and how much of the run
    is behind them.
    """
    state = store.standing()
    if not state.get('seed'):
        return {'run': None}
    version = state.get('check_schema_version')
    if version is not None and int(version or 0) > CHECK_SCHEMA_VERSION:
        # A run written by a newer launcher. Drawing it from an older
        # reading of what a check is would show the wrong count against
        # every mission, and quietly.
        return {
            'run': None,
            'refused': 'This run was made by a newer launcher.',
        }
    installed = _missions_by_code()
    tiles = (
        progress.grid_states(state)
        if str(state.get(MODE_KEY) or '') == GRID_MODE else {}
    )
    listed = [
        _mission_view(state, code, installed, tiles)
        for code in progress.order(state)
    ]
    won = [mission for mission in listed if mission['complete']]
    goal = int(state.get('mission_goal') or len(listed) or 0)
    return {
        'run': {
            'seed': str(state.get('seed') or ''),
            'mode': str(state.get(MODE_KEY) or ''),
            # What the launcher is set to now, which is not always what
            # this run was made as: a mode can be changed after a run
            # exists, and the run keeps the order it was dealt.
            'standing_mode': str(_settings().get(MODE_KEY) or ''),
            'campaign': str(state.get('campaign_filter') or ''),
            'goal': goal,
            'won': len(won),
            'rewards': len(state.get('earned_rewards') or ()),
            'finished': bool(listed) and len(won) >= goal,
            'next': progress.next_code(state),
            'missions': listed,
        },
    }


@action('campaign.settings', 'How the next campaign run will be generated')
def settings():
    return _answer(_settings())


@action('campaign.catalogue', 'What one campaign setting may name')
def catalogue(name=''):
    """Return one named list, whole.

    Whole rather than searched, because a screen filters it as somebody
    types and the launcher is not the place to be asked once a letter.
    Which is why it is a reading of its own: the settings are read again
    after every change, and a few hundred entries have no business
    coming back with them.
    """
    wanted = str(name or '')
    if wanted not in CATALOGUE_NAMES:
        raise ApiError(f'There is no {wanted or "unnamed"} catalogue')
    return {
        'name': wanted,
        'entries': [
            dict(entry) for entry in campaign_catalogues.catalogue(wanted)
        ],
    }


@action('campaign.use_setting', 'Change one campaign setting', kind=COMMAND)
def use_setting(name='', value=None):
    """Keep one campaign setting and answer with all of them."""
    config = _settings()
    CAMPAIGN.write(config, name, value)
    _keep(config)
    return _answer(config)

