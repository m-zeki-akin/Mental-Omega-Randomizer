"""What a campaign run is set up with, before a seed is generated.

The three campaign modes share almost every setting -- they are the same
campaign in a different order -- so one screen answers for all three, and
the table says which of the rows belong to Grid alone.

Nothing here generates a seed or touches one that exists. A run that has
been generated keeps the settings it was generated with; these describe
the next one, which is why they are settings rather than run state.
"""

from randomizer.ui.campaign_catalogues import (
    CATALOGUE_NAMES,
    catalogue as catalogue_entries,
    labels,
)
from randomizer.ui.campaign_settings import (
    BY_KEY,
    CHOICE,
    ENEMY_CAPACITY,
    ENEMY_SCALING,
    NUMBER,
    SEARCH,
    SET,
    SWITCH,
    TEXT,
    WEIGHTS,
    full_key,
    rows_for,
)
from .contract import COMMAND, ApiError, action


# What a named list may hold. Longer than any catalogue the installed
# rules offer, and short enough that a settings file cannot be filled
# with one by a screen that has gone wrong.
MAXIMUM_NAMED = 1000
MAXIMUM_NAME_LENGTH = 128


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
        # A number that was never written answers what the launcher
        # would use, not the bottom of its range: an unset weight is a
        # full one, and reading it as zero would say the opposite.
        default = row.get('default', row['minimum'])
        try:
            number = int(held)
        except (TypeError, ValueError):
            number = default
        return max(row['minimum'], min(_ceiling(config, row), number))
    if row['kind'] == TEXT:
        return str(held or '').strip()[:row['maximum_length']]
    if row['kind'] == SET:
        known = [entry['id'] for entry in row['catalogue']]
        if not isinstance(held, (list, tuple)):
            return list(known)
        chosen = {str(item) for item in held}
        # A list that says everything means everything there is now,
        # which is the whole point of writing it that way.
        if row.get('wildcard') and row['wildcard'] in chosen:
            return list(known)
        return [item for item in known if item in chosen]
    if row['kind'] == SEARCH:
        if not isinstance(held, (list, tuple)):
            return []
        return [
            entry['id'] for entry in labels(row['catalogue_name'], held)
        ]
    if row['kind'] == CHOICE:
        wanted = str(held or '')
        return wanted if wanted in row['choices'] else row['choices'][0]
    # Every kind is named above. A group of weights is the one row
    # that holds nothing of its own, and asking it for a value used to
    # fall through to the choices a group has none of -- which is a
    # KeyError, which is a screen that says nothing at all.
    raise ApiError(f'{row["label"]} is not one setting with one value')


def _ceiling(config, row):
    """Return the highest a number may go as the rest of the settings stand.

    Most numbers have one ceiling and the row says what it is. The
    enemy's total is the exception: what it can reach is the capacity of
    the bonuses that are actually allowed, so a run with two thirds of
    them turned off cannot collect what the row's own maximum says. The
    generator has always clamped it there; this is the screen no longer
    offering what would be quietly cut.

    With nothing allowed the capacity is zero, and a zero ceiling would
    trap the setting: the list of bonuses is shown only while the total
    is not zero, so a player who had turned every one of them off could
    never turn one back on. The row's own maximum stands in for that,
    and the help beside it already says the number means nothing while
    nothing is allowed.
    """
    if row.get('ceiling') != ENEMY_CAPACITY:
        return row['maximum']
    from randomizer.rewards.enemy_scaling import enemy_buff_capacity

    block = config
    for step in ENEMY_SCALING.split('.'):
        held = block.get(step)
        block = held if isinstance(held, dict) else {}
    capacity = enemy_buff_capacity(block)
    return min(row['maximum'], capacity) if capacity else row['maximum']


def _weights(config, row):
    """Return one group of weights, each with its share of the group.

    The share is what a weight means: 50 beside two 100s comes up a
    fifth of the time, and neither the 50 nor the 100 says so on its
    own. A group that is all zeroes has no shares -- nothing in it
    comes up at all.
    """
    entries = []
    for key in row['entries']:
        other = BY_KEY.get(key)
        if other is None:
            continue
        entries.append({
            'key': key,
            'label': other['label'],
            'help': other['help'],
            'value': _value(config, other),
            'minimum': other['minimum'],
            'maximum': other['maximum'],
            'step': other['step'],
        })
    total = sum(entry['value'] for entry in entries)
    for entry in entries:
        entry['share'] = (
            round(100 * entry['value'] / total) if total else 0
        )
    return entries


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
    }
    # A group of weights holds no value of its own: what it has is the
    # settings it draws, and each of those is written by its own name.
    if row['kind'] == WEIGHTS:
        shown['entries'] = _weights(config, row)
        return shown
    shown['value'] = (
        '' if standing and row.get('blank_while_generated')
        else _value(config, row)
    )
    if row['kind'] == NUMBER:
        shown.update(
            minimum=row['minimum'],
            maximum=_ceiling(config, row),
            step=row['step'],
        )
    elif row['kind'] == CHOICE:
        shown['choices'] = list(row['choices'])
    elif row['kind'] == TEXT:
        shown['maximum_length'] = row['maximum_length']
    elif row['kind'] == SET:
        shown['catalogue'] = [dict(entry) for entry in row['catalogue']]
    elif row['kind'] == SEARCH:
        # The list itself does not come with the settings: it is a few
        # hundred entries, it is the same on every reading, and a screen
        # asks for it once. What comes is what has been picked, named.
        shown['catalogue_name'] = row['catalogue_name']
        shown['catalogue_size'] = len(
            catalogue_entries(row['catalogue_name'])
        )
        shown['chosen'] = labels(row['catalogue_name'], shown['value'])
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


def _needed(config, row):
    """Whether a row means anything as the other settings stand.

    A row can name another setting it depends on: True for "holds
    anything at all", or a value it has to hold. Hidden rather than
    greyed out, because a control that cannot do anything is one more
    thing on a screen to read past.
    """
    wanted = row.get('needs')
    if not wanted:
        return True
    key, expected = wanted
    other = BY_KEY.get(key)
    if other is None or other['kind'] == WEIGHTS:
        return True
    held = _value(config, other)
    return bool(held) if expected is True else held == expected


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
                'settings': [
                    _shown(row, config, standing) for row in shown
                ],
            }
            for name, shown in (
                (name, [row for row in rows if _needed(config, row)])
                for name, rows in rows_for(mode)
            )
            # A section whose every row is about something turned off is
            # a heading with nothing under it.
            if shown
        ],
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
        'entries': [dict(entry) for entry in catalogue_entries(wanted)],
    }


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
        kept = max(row['minimum'], min(_ceiling(config, row), number))
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
        # All of them is kept as all of them, rather than as a list of
        # everything there happens to be today.
        if row.get('wildcard') and len(kept) == len(row['catalogue']):
            kept = [row['wildcard']]
    elif row['kind'] == SEARCH:
        if not isinstance(value, (list, tuple)):
            raise ApiError(f'{row["label"]} needs a list of names')
        # A name the installed rules do not know is kept rather than
        # dropped: a submod that renames a unit should not quietly empty
        # a list somebody built, and the screen shows the name as it is
        # so it can be taken out on purpose.
        kept = [
            entry['id']
            for entry in labels(row['catalogue_name'], value)
            if len(entry['id']) <= MAXIMUM_NAME_LENGTH
        ][:MAXIMUM_NAMED]
    elif row['kind'] == WEIGHTS:
        raise ApiError(
            f'{row["label"]} is a group of settings; change one of them '
            'by its own name'
        )
    else:
        kept = str(value or '')
        if kept not in row['choices']:
            raise ApiError(f'{row["label"]} has no {kept or "unnamed"} choice')
    _where(config, row, make=True)[row['key']] = kept
    _keep(config)
    return _answer(config)
