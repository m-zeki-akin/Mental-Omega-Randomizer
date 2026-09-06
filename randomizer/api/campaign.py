"""What a campaign run is set up with, before a seed is generated.

The three campaign modes share almost every setting -- they are the same
campaign in a different order -- so one screen answers for all three, and
the table says which of the rows belong to Grid alone.

Nothing here generates a seed or touches one that exists. A run that has
been generated keeps the settings it was generated with; these describe
the next one, which is why they are settings rather than run state.
"""

from randomizer.ui.campaign_settings import (
    BY_KEY,
    CHOICE,
    GENERATION,
    NUMBER,
    SWITCH,
    rows_for,
)
from .contract import COMMAND, ApiError, action


def _settings():
    from randomizer.config.player import load_config

    return load_config()


def _keep(config):
    from randomizer.config.player import save_config

    save_config(config)


def _where(config, row):
    """Return the part of the settings a row lives in."""
    if row['where'] == GENERATION:
        block = config.get('generation')
        return block if isinstance(block, dict) else {}
    return config


def _value(config, row):
    """Return what a row holds, as the kind of thing the row says it is."""
    held = _where(config, row).get(row['key'])
    if row['kind'] == SWITCH:
        return bool(held)
    if row['kind'] == NUMBER:
        try:
            number = int(held)
        except (TypeError, ValueError):
            number = row['minimum']
        return max(row['minimum'], min(row['maximum'], number))
    wanted = str(held or '')
    return wanted if wanted in row['choices'] else row['choices'][0]


def _shown(row, config):
    shown = {
        'key': row['key'],
        'label': row['label'],
        'kind': row['kind'],
        'help': row['help'],
        'value': _value(config, row),
    }
    if row['kind'] == NUMBER:
        shown.update(
            minimum=row['minimum'], maximum=row['maximum'], step=row['step'],
        )
    elif row['kind'] == CHOICE:
        shown['choices'] = list(row['choices'])
    return shown


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
    return {
        'mode': mode,
        'sections': [
            {
                'name': name,
                'settings': [_shown(row, config) for row in rows],
            }
            for name, rows in rows_for(mode)
        ],
    }


@action('campaign.settings', 'How the next campaign run will be generated')
def settings():
    return _answer(_settings())


@action('campaign.use_setting', 'Change one campaign setting', kind=COMMAND)
def use_setting(name='', value=None):
    """Keep one setting, as the kind of thing its row says it is.

    A number out of range is clamped rather than refused -- a control
    cannot ask for what the launcher would not offer, and a settings file
    already holding one is worth quietly correcting. A choice that is not
    one of the choices is a refusal, because there is nothing sensible to
    correct it to.
    """
    key = str(name or '')
    row = BY_KEY.get(key)
    if row is None:
        raise ApiError(f'There is no {key or "unnamed"} campaign setting')
    config = _settings()
    if row['kind'] == SWITCH:
        if value is None:
            raise ApiError(f'Say whether {row["label"]} is on or off')
        kept = bool(value)
    elif row['kind'] == NUMBER:
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ApiError(f'{row["label"]} needs a number') from None
        kept = max(row['minimum'], min(row['maximum'], number))
    else:
        kept = str(value or '')
        if kept not in row['choices']:
            raise ApiError(f'{row["label"]} has no {kept or "unnamed"} choice')
    if row['where'] == GENERATION:
        config.setdefault('generation', {})[key] = kept
    else:
        config[key] = kept
    _keep(config)
    return _answer(config)
