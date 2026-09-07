"""What a Shop run will be started with, before there is a run.

Two halves, and they belong together because they are the same decision:
how fast a run goes -- income, stage length, how hard the enemy answers --
and which optional trades are on. Both describe the *next* run. A run that
has begun keeps the rules it began with, snapshotted into its own
settings, and nothing here can reach it.

That is also why these are settings rather than run state: they outlive
the run they were used for, and both windows read them from the same
place. Moving a control in one and opening the other shows the move.
"""

from randomizer.shop.config import (
    MODIFIER_SETTING_KEY,
    PACING_LABELS,
    PACING_SETTING_KEY,
    RUN_PACING_SETTINGS,
    SHOP_CONFIG,
    configured_modifiers,
    configured_pacing,
    pacing_to_store,
)
from randomizer.shop.modifiers import (
    format_difficulty,
    pacing_gem_scale_percent,
    run_difficulty,
)
from randomizer.ui.shop_settings import SECTIONS

from .contract import COMMAND, ApiError, action
from .settings import Settings


# The rest of the setup -- the seed, the faction pool, which missions a
# run may be dealt, which rewards are kept off the shelf -- is a table
# like the campaign's, answered by the same piece in the middle.
SHOP = Settings(SECTIONS)


def _settings():
    from randomizer.config.player import load_config

    return load_config()


def _keep(config):
    from randomizer.config.player import save_config

    save_config(config)


def _step(key):
    """How far one press of a control moves it, as the classic window has it."""
    return 10 if key.endswith('_percent') else 1


def _pacing(chosen):
    return [
        {
            'key': key,
            'label': PACING_LABELS.get(key, key),
            'value': chosen[key],
            'baseline': getattr(SHOP_CONFIG, field),
            'minimum': minimum,
            'maximum': maximum,
            'step': _step(key),
        }
        for key, (field, minimum, maximum) in RUN_PACING_SETTINGS.items()
    ]


def _modifiers(enabled):
    return [
        {
            'id': modifier_id,
            'name': definition.display_name,
            'description': definition.description,
            'enabled': modifier_id in enabled,
        }
        for modifier_id, definition in SHOP_CONFIG.modifiers.items()
    ]


def _answer(config):
    chosen = configured_pacing(config, SHOP_CONFIG)
    enabled = configured_modifiers(config, SHOP_CONFIG)
    return {
        'pacing': _pacing(chosen),
        'modifiers': _modifiers(enabled),
        # What the pacing adds up to. The modifiers deliberately do not
        # count: each pairs an advantage with a drawback.
        'difficulty': format_difficulty(run_difficulty((), chosen)),
        'gem_scale_percent': pacing_gem_scale_percent(chosen),
        'default': not pacing_to_store(chosen, SHOP_CONFIG) and not enabled,
        'sections': SHOP.answer(config),
    }


@action('shop.settings', 'How the next Shop run will be paced, and its trades')
def settings():
    return _answer(_settings())


@action(
    'shop.use_pacing',
    'Set one pacing control for the next Shop run',
    kind=COMMAND,
)
def use_pacing(name='', value=None):
    """Keep one pacing choice.

    The value is taken as an exact number rather than a step, so the
    control that sends it decides how it moves and this decides only what
    is allowed. Out of range is clamped rather than refused: a control
    cannot ask for something the launcher would not offer, and a settings
    file that already holds one is worth correcting quietly.
    """
    key = str(name or '')
    if key not in RUN_PACING_SETTINGS:
        raise ApiError(f'There is no {key or "unnamed"} pacing setting')
    try:
        wanted = int(value)
    except (TypeError, ValueError):
        raise ApiError(f'{PACING_LABELS.get(key, key)} needs a number') from None
    _field, minimum, maximum = RUN_PACING_SETTINGS[key]
    config = _settings()
    chosen = configured_pacing(config, SHOP_CONFIG)
    chosen[key] = max(minimum, min(maximum, wanted))
    config[PACING_SETTING_KEY] = pacing_to_store(chosen, SHOP_CONFIG)
    _keep(config)
    return _answer(config)


@action(
    'shop.use_modifier',
    'Turn one optional run modifier on or off',
    kind=COMMAND,
)
def use_modifier(name='', enabled=None):
    modifier_id = str(name or '')
    if modifier_id not in SHOP_CONFIG.modifiers:
        raise ApiError(f'There is no {modifier_id or "unnamed"} modifier')
    if enabled is None:
        raise ApiError('Say whether the modifier is on or off')
    config = _settings()
    chosen = set(configured_modifiers(config, SHOP_CONFIG))
    if bool(enabled):
        chosen.add(modifier_id)
    else:
        chosen.discard(modifier_id)
    config[MODIFIER_SETTING_KEY] = [
        known for known in SHOP_CONFIG.modifiers if known in chosen
    ]
    _keep(config)
    return _answer(config)


@action('shop.use_setting', 'Change one Shop Mode setting', kind=COMMAND)
def use_setting(name='', value=None):
    """Keep one of the settings the pacing controls are not.

    Separate from ``shop.use_pacing`` because they are different
    questions: pacing is a number with a baseline behind it that scores
    towards a run's difficulty, and these are the plain settings a run is
    dealt from.
    """
    config = _settings()
    SHOP.write(config, name, value)
    _keep(config)
    return _answer(config)


@action(
    'shop.reset_setup',
    'Put the next run back to the configured pacing with no modifiers',
    kind=COMMAND,
)
def reset_setup():
    """Forget every choice, which is what leaves the baseline showing.

    Nothing is written as the baseline itself. An unset pacing key means
    whatever shop_mode.json says today, so a run started after a rebalance
    is paced by the new number rather than by a copy of the old one.
    """
    config = _settings()
    config[PACING_SETTING_KEY] = {}
    config[MODIFIER_SETTING_KEY] = []
    _keep(config)
    return _answer(config)
