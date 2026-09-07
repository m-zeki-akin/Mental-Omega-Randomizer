"""What a campaign run is set up with, before a seed is generated.

The three campaign modes share almost every setting -- they are the same
campaign in a different order -- so one screen answers for all three, and
the table says which of the rows belong to Grid alone.

Nothing here generates a seed or touches one that exists. A run that has
been generated keeps the settings it was generated with; these describe
the next one, which is why they are settings rather than run state.

How a table becomes a reply is not here either: that is the same question
for every setup screen, and it is answered once in ``settings``.
"""

from randomizer.ui import campaign_catalogues
from randomizer.ui.campaign_catalogues import CATALOGUE_NAMES
from randomizer.ui.campaign_settings import (
    ENEMY_CAPACITY,
    ENEMY_SCALING,
    SECTIONS,
)

from .contract import COMMAND, ApiError, action
from .settings import Settings


def _enemy_capacity(config, row):
    """Return what the bonuses actually allowed could add up to.

    The enemy's total is capped by them: turning most of them off lowers
    what a run could ever hand out, and the generator has always clamped
    the number there. A screen going on offering the full range would be
    offering a number that is quietly cut on the way to the seed.

    With nothing allowed the capacity is nought, and a nought ceiling
    would trap the setting -- the bonuses are shown only while the total
    is not nought, so a player who had turned every one off could never
    turn one back on. The row's own maximum stands in for that, and the
    help beside it already says the number means nothing while nothing is
    allowed.
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

