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
    NUMBER,
    SET,
    SWITCH,
    TEXT,
    full_key,
    rows_for,
)
from .contract import COMMAND, ApiError, action


def _settings():
    from randomizer.config.player import load_config

    return load_config()


def _keep(config):
    from randomizer.config.player import save_config

    save_config(config)


def _where(config, row, *, make=False):
    """Return the block of the settings a row lives in.

    A row says where it lives as a path, because some of them live in a
    block inside a block. Reading a block that is not there answers an
    empty one; writing makes it.
    """
    block = config
    for step in filter(None, str(row['where']).split('.')):
        held = block.get(step)
        if not isinstance(held, dict):
            if not make:
                return {}
            held = {}
            block[step] = held
        block = held
    return block


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
    if row['kind'] == TEXT:
        return str(held or '').strip()[:row['maximum_length']]
    if row['kind'] == SET:
        known = [entry['id'] for entry in row['catalogue']]
        chosen = set(held) if isinstance(held, (list, tuple)) else set(known)
        return [item for item in known if item in chosen]
    wanted = str(held or '')
    return wanted if wanted in row['choices'] else row['choices'][0]


def _standing():
    """Return the seed the classic window has generated, if one stands."""
    from .launcher import _campaign_seed

    return str((_campaign_seed() or {}).get('seed') or '')


def _shown(row, config, standing=''):
    shown = {
        'key': full_key(row),
        'label': row['label'],
        'kind': row['kind'],
        'help': row['help'],
        'value': (
            '' if standing and row.get('blank_while_generated')
            else _value(config, row)
        ),
    }
    if row['kind'] == NUMBER:
        shown.update(
            minimum=row['minimum'], maximum=row['maximum'], step=row['step'],
        )
    elif row['kind'] == CHOICE:
        shown['choices'] = list(row['choices'])
    elif row['kind'] == TEXT:
        shown['maximum_length'] = row['maximum_length']
    elif row['kind'] == SET:
        shown['catalogue'] = [dict(entry) for entry in row['catalogue']]
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
    # A seed already generated is a run in progress, and a run in progress
    # is why the seed box is empty in the classic window. Both windows say
    # the same thing about it, and this is what it is.
    standing = _standing()
    return {
        'mode': mode,
        'generated_seed': standing,
        'sections': [
            {
                'name': name,
                'settings': [_shown(row, config, standing) for row in rows],
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
    elif row['kind'] == TEXT:
        # Trimmed and capped rather than refused: what a player typed is
        # worth keeping even when they typed a space at the end of it.
        kept = str(value or '').strip()[:row['maximum_length']]
    elif row['kind'] == SET:
        if not isinstance(value, (list, tuple)):
            raise ApiError(f'{row["label"]} needs a list of what is on')
        wanted = {str(item) for item in value}
        kept = [
            entry['id'] for entry in row['catalogue']
            if entry['id'] in wanted
        ]
    else:
        kept = str(value or '')
        if kept not in row['choices']:
            raise ApiError(f'{row["label"]} has no {kept or "unnamed"} choice')
    _where(config, row, make=True)[row['key']] = kept
    _keep(config)
    return _answer(config)
