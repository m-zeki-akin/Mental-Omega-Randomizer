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
from randomizer.shop.model import SHOP_ACCESS_REWARD_MODE
from randomizer.shop.modifiers import (
    format_difficulty,
    pacing_gem_scale_percent,
    run_difficulty,
)
from randomizer.ui.shop_settings import SECTIONS

from .contract import COMMAND, ApiError, action
from .settings import Settings, about


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
        # Whose settings these are: the roguelike pair's, drawn as this
        # run's own beside what it shares with the skirmish.
        'about': about('Shop Mode'),
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


# --- the run ----------------------------------------------------------
#
# Shop Mode's own half. The setup above says what the *next* run will be;
# this is the one being played: what it has, what it is offered, what is
# on the shelf, and the mission it is about to start.
#
# Everything here reads the domain rather than the old window. A run is
# started, chosen from, bought from and given up through
# ShopProgressionService, which is the same object the window drives.


def _repository():
    from randomizer.shop.persistence import ShopRepository

    return ShopRepository()


def _service():
    from randomizer.shop.service import ShopProgressionService

    return ShopProgressionService(_repository())


def _maker(config=None):
    """Return a launcher with nothing drawn, for the things that need one."""
    from randomizer.campaign import generator

    from .campaign import _settings as campaign_settings

    return generator.build(
        config or campaign_settings(), generator.installed_missions()
    )


def _mission_titles():
    from randomizer.campaign import generator

    return {
        str(mission.get('code') or ''): str(mission.get('title') or '')
        for mission in generator.installed_missions()
    }


def _offer_view(offer, run, titles):
    from randomizer.shop.missions import mission_difficulty

    code = offer.mission_code
    return {
        'code': code,
        'name': titles.get(code) or code,
        'economy': offer.economy_class.value,
        'difficulty': mission_difficulty(
            run.seed, run.stage, code, run_length=run.run_length,
        ),
        'chosen': code == run.selected_mission_code,
    }


def _shelf_view(profile, run):
    """Return the three shelves, each row with what it costs right now."""
    from randomizer.shop.catalogue import canonical_reward_for_id
    from randomizer.shop.economy import run_reward_price
    from randomizer.shop.shelf import shop_shelf

    units, powers, upgrades = shop_shelf(profile, run)
    def rows(entries):
        listed = []
        for entry in entries:
            reward = canonical_reward_for_id(entry.reward_id)
            listed.append({
                'reward_id': entry.reward_id,
                'name': str(reward.get('name') or entry.reward_id),
                'target': entry.target_id or '',
                'kind': entry.reward_type.value,
                'price': run_reward_price(
                    entry,
                    shop_discount_level=profile.upgrade_level('shop_discount'),
                    modifiers=run.modifiers,
                    specialization_level=profile.upgrade_level(
                        'discount_specialization'
                    ),
                ),
                'bought': entry.reward_id in run.stage_shelf_purchases,
            })
        return listed

    return {
        'units': rows(units),
        'powers': rows(powers),
        'upgrades': rows(upgrades),
    }


def _run_view(profile, run):
    from randomizer.shop.summary import (
        run_summary_lines,
        shop_run_progress_text,
    )
    from randomizer.shop.transitions import maximum_run_lives

    if run is None:
        return None
    titles = _mission_titles()
    return {
        'run_id': run.run_id,
        'seed': run.seed,
        'status': run.status.value,
        'active': run.status.name == 'ACTIVE',
        'stage': run.stage,
        'run_length': run.run_length,
        'endless': run.endless,
        'coins': run.run_coins,
        'lives': maximum_run_lives(profile),
        'lives_used': run.emergency_revivals_used,
        'progress': shop_run_progress_text(run, profile),
        'offers': [_offer_view(one, run, titles) for one in run.mission_offers],
        'selected': run.selected_mission_code or '',
        'committed': run.mission_committed,
        'rerolls_used': run.rerolls_used,
        'shelf': _shelf_view(profile, run),
        'summary': list(run_summary_lines(profile, run, titles)),
    }


@action('shop.profile', 'What every Shop run so far has left behind')
def profile():
    stored = _repository().load_profile()
    return {
        'meta_coins': stored.meta_coins,
        'runs_started': stored.lifetime_runs_started,
        'runs_completed': stored.lifetime_runs_completed,
        'missions_completed': stored.lifetime_missions_completed,
        'units': list(stored.permanent_unit_unlocks),
        'upgrades': dict(stored.permanent_upgrades),
        'salvaged': stored.salvaged_run_coins,
    }


@action('shop.run', 'The Shop run being played, or nothing')
def run():
    stored_profile, stored_run = _repository().load()
    return _run_view(stored_profile, stored_run)


def _new_run_settings(maker, config):
    """Return the reward settings a Shop run is started under.

    The window's own list, read from the settings rather than from its
    boxes: Shop Mode turns off the campaign's tuning wholesale, because a
    run's difficulty is its pacing and its shelf rather than the dials
    another mode is played with.
    """
    from randomizer.rewards.catalogue import BUFF_TYPES, POWER_BUFF_TYPES

    settings = dict(maker.current_reward_settings())
    settings.update({
        'randomize_unit_access': True,
        'start_with_tier_one_units': True,
        'start_with_tier_one_defenses': True,
        'starting_reward_count': 0,
        'starting_unlock_rewards': [],
        'include_defensive_buildings': True,
        'include_special_buildings': True,
        'include_special_rewards': True,
        'unlimited_hero_units': False,
        'share_chaos_role_buffs': False,
        'buff_allied_helpers': False,
        'failure_assistance': False,
        'include_buff_rewards': True,
        'include_superweapon_rewards': True,
        'include_secondary_superweapon_rewards': True,
        'include_aid_power_rewards': True,
        'include_power_buff_rewards': True,
        'enabled_reward_types': [
            'access', 'buff', 'superweapon',
            'secondary_superweapon', 'aid_power', 'power_buff',
        ],
        'enabled_buff_types': [one['id'] for one in BUFF_TYPES],
        'enabled_power_buff_types': [one['id'] for one in POWER_BUFF_TYPES],
        'excluded_unit_access_ids': [],
        'excluded_superweapon_ids': [],
        'excluded_unit_buff_types': {},
        'excluded_power_buff_types': {},
    })
    scaling = dict(settings.get('enemy_scaling') or {})
    scaling['maximum_total_buffs'] = 0
    settings['enemy_scaling'] = scaling
    settings.update(configured_pacing(_settings(), config))
    return settings


@action('shop.start', 'Begin a Shop run', kind=COMMAND)
def start(seed=''):
    """Start a run out of the settings, with no window anywhere in it."""
    import uuid

    from randomizer.shop.config import SHOP_CONFIG
    from randomizer.shop.new_run import plan_new_run
    from randomizer.shop.transitions import ShopTransitionError

    from . import mission_session

    if mission_session.running():
        raise ApiError('A mission is already being played')
    config = _settings()
    maker = _maker(config)
    missions = list(maker.missions or ())
    if not missions:
        raise ApiError('No missions are installed here')
    wanted = str(seed or '').strip() or uuid.uuid4().hex[:16].upper()
    stored_profile = _repository().load_profile()
    settings = _new_run_settings(maker, SHOP_CONFIG)
    settings['shop_faction_filter'] = 'All Campaigns'
    try:
        planned = plan_new_run(
            run_id=uuid.uuid4().hex,
            seed=wanted,
            profile=stored_profile,
            settings=settings,
            mission_pool=missions,
            faction_filter='All Campaigns',
            starting_unit_markers=maker.starting_tier_one_unit_ids_for_seed(
                wanted, settings
            ),
            starting_defense_markers=(
                maker.starting_tier_one_defense_ids_for_seed(
                    settings, seed=wanted
                )
            ),
            selected_loadout=tuple(stored_profile.permanent_unit_unlocks),
            modifiers=configured_modifiers(config),
            reward_mode=SHOP_ACCESS_REWARD_MODE,
            config=SHOP_CONFIG,
        )
        _service().start_run(**planned)
    except (ShopTransitionError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    return {'seed': wanted}


@action('shop.select', 'Choose which mission this stage is played on',
        kind=COMMAND)
def select(code=''):
    from randomizer.shop.transitions import ShopTransitionError

    try:
        _service().select_mission(str(code or '').strip().upper())
    except (ShopTransitionError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    return {'code': str(code or '').strip().upper()}


@action('shop.buy', 'Buy one thing off the shelf', kind=COMMAND)
def buy(reward_id=''):
    from randomizer.shop.transitions import ShopTransitionError

    try:
        validation = _service().purchase_run_reward(str(reward_id or ''))
    except (ShopTransitionError, ValueError, KeyError) as exc:
        raise ApiError(str(exc)) from exc
    if not validation.allowed:
        raise ApiError(str(validation.reason or 'That cannot be bought'))
    return {'reward_id': str(reward_id or '')}


@action('shop.give_up', 'End the Shop run being played', kind=COMMAND)
def give_up():
    from randomizer.shop.transitions import ShopTransitionError

    try:
        _service().give_up_run()
    except (ShopTransitionError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    return {'ended': True}


def _launch_maker(stored_profile, stored_run):
    """Return a launcher that writes a Shop mission rather than a campaign one.

    The campaign's own machinery decides how a mission is written -- the
    map, the markers, the rules -- and Shop Mode changes only what it is
    written *with*. So the four answers that differ are answered from the
    run, and everything else is inherited.
    """
    from randomizer.shop.catalogue import shop_catalogue_by_reward_id
    from randomizer.shop.launch_rules import (
        enemy_scaling_entries,
        launch_rewards,
        reward_settings,
    )

    base = _maker()
    entries = shop_catalogue_by_reward_id()

    class ShopLaunch(type(base)):
        def active_reward_mode(self):
            return SHOP_ACCESS_REWARD_MODE

        def active_progression_mode(self):
            return 'Shop Mode'

        def active_launch_seed(self):
            return stored_run.seed

        def active_launch_campaign_filter(self):
            return stored_run.campaign_filter

        def launch_state_document(self):
            return {
                'seed': stored_run.seed,
                'campaign_filter': stored_run.campaign_filter,
                'progression_mode': 'Shop Mode',
                'completed_missions': list(stored_run.completed_missions),
            }

        def active_reward_settings(self):
            return reward_settings(stored_run)

        def active_launch_rewards(self):
            return launch_rewards(stored_run, stored_profile, entries)

        def launch_rewards_for_mission(self, code):
            return self.active_launch_rewards()

        def active_enemy_scaling_entries(self):
            return enemy_scaling_entries(stored_run)

    from randomizer.campaign import generator

    return ShopLaunch(
        _settings(), generator.installed_missions(), None,
    )


@action('shop.launch', 'Play the mission this Shop stage is on', kind=COMMAND)
def launch():
    from randomizer.core.paths import GAME_EXE, GAME_LAUNCHER_EXE
    from randomizer.shop.transitions import ShopTransitionError

    from . import mission_session, session
    from .campaign import _hook_for, _missions_by_code

    stored_profile, stored_run = _repository().load()
    if stored_run is None or stored_run.status.name != 'ACTIVE':
        raise ApiError('There is no Shop run to play a mission of')
    if mission_session.running():
        raise ApiError('A mission is already being played')
    if session.running():
        raise ApiError('A skirmish battle is being played')
    code = str(stored_run.selected_mission_code or '')
    if not code:
        raise ApiError('Choose which mission this stage is played on first')
    mission = _missions_by_code().get(code)
    if not mission or not mission.get('scenario'):
        raise ApiError(f'{code} is not installed here')
    missing = [
        path for path in (GAME_LAUNCHER_EXE, GAME_EXE) if not path.exists()
    ]
    if missing:
        raise ApiError(
            'The game is not where the launcher expects it: '
            + ', '.join(path.name for path in missing)
        )
    # The stage is committed before the game opens, the way the window
    # does it: a mission played against an uncommitted stage would be a
    # victory the run refuses to record.
    try:
        if not stored_run.mission_committed:
            _service().commit_mission(code)
    except (ShopTransitionError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    _stored_profile, stored_run = _repository().load()
    maker = _launch_maker(stored_profile, stored_run)
    prepared = maker.prepare_mission_launch_files(
        mission,
        None,
        maker.get_selected_difficulty_value(),
        maker.get_selected_game_speed_value(),
    )
    hook = _hook_for(mission, prepared)
    try:
        process, _command = maker.spawn_game_process()
    except OSError as exc:
        maker.cleanup_generated_root_maps()
        maker.disable_generated_rules_for_client()
        raise ApiError(f'The game would not start: {exc}') from exc
    maker.remember_mission_started(mission)
    mission_session.start(hook, stored_run.seed, process)
    return {
        'code': code,
        'name': str(mission.get('title') or code),
        'watched': bool(hook.get('markers')),
    }


@action('shop.session', 'What the Shop mission being played is doing')
def playing():
    from . import mission_session

    stored_profile, stored_run = _repository().load()
    if stored_run is None:
        return {'playing': False, 'finished': None}
    return mission_session.poll(_launch_maker(stored_profile, stored_run))
