"""Static player-owned TechnoType roster loading and validation."""

from __future__ import annotations

import traceback
from functools import lru_cache
from math import isfinite
from pathlib import Path
from statistics import median

from randomizer.core.paths import APP_DIR, FROZEN, SOURCE_DIR


# What is left of a 494 KB bake of every player clone's complete stat line.
# The bake was a copy of stock rules with the reviewed clone policy applied,
# and the policy is in template_policy.py, so all of it could be rebuilt from
# the rules the installation loads -- measured at 326 of 326 sections
# reproduced with no differences. Two things could not: which units get a
# clone at all, and the six bodies that exist only inside maps.
ROSTER_REGISTRY_FILENAME = 'RandomizerUnits.ini'
MAP_ONLY_SOURCE_FILENAME = 'RandomizerMapOnlySources.ini'
ROSTER_FILENAMES = (ROSTER_REGISTRY_FILENAME, MAP_ONLY_SOURCE_FILENAME)
# Files the bake used to occupy. Removed from a packaged install on load;
# nothing reads them and they are half a megabyte each time.
OBSOLETE_ROSTER_FILENAMES = (
    'RandomizerInfantry.ini',
    'RandomizerHeroes.ini',
    'RandomizerVehicles.ini',
    'RandomizerShips.ini',
    'RandomizerAircraft.ini',
    'RandomizerDefensesAndSpecialBuildings.ini',
)
ROSTER_CATEGORIES = {
    'infantry': 'InfantryTypes',
    'units': 'VehicleTypes',
    'aircraft': 'AircraftTypes',
    'defenses': 'BuildingTypes',
    'special_buildings': 'BuildingTypes',
}
MAX_PLAYER_BUILD_TIME_MULTIPLIER = 10.0
BUILD_TIME_MULTIPLIER_KEYS = frozenset({
    'buildtimemultiplier',
    'buildtime.multiplefactory',
})


def randomizer_unit_id(source_id):
    return f'MORP{str(source_id or "").strip().upper()}'


def _retire_obsolete_visible_rosters():
    """Delete the old editable stat bake from a packaged install.

    Half a megabyte per installation of clone stat lines nothing reads any
    more. They were briefly renamed ``.replaced`` instead of deleted, which
    only meant the same bytes with a longer name: a player edit to them was
    authoritative for stats the launcher now takes from the installed rules,
    so there is nothing in them left to preserve. Both forms go.
    """
    folder = APP_DIR / 'configs'
    if not FROZEN or not folder.is_dir():
        return []
    retired = []
    for name in OBSOLETE_ROSTER_FILENAMES:
        for path in (folder / name, folder / (name + '.replaced')):
            if not path.is_file():
                continue
            try:
                path.unlink()
            except OSError:
                continue
            retired.append(path.name)
    return retired


def _active_roster_paths():
    """Return the committed roster files -- always the bundled ones.

    These were copied into the game folder and treated as authoritative once
    there, which was right while they carried every clone's stat line: a
    player who wanted their Rhino retuned had somewhere to do it. They no
    longer carry stats. What they carry now is which units the randomizer
    clones, and six bodies no rules file contains, so an editable copy would
    only be a way to award yourself units.
    """
    _retire_obsolete_visible_rosters()
    return tuple(SOURCE_DIR / 'configs' / name for name in ROSTER_FILENAMES)


def _read_sections(path: Path):
    sections = {}
    current = None
    for raw_line in path.read_text(encoding='utf-8-sig').splitlines():
        stripped = raw_line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            current = stripped[1:-1].strip()
            sections[current] = {}
            continue
        if current is None or not stripped or stripped.startswith(';') or '=' not in raw_line:
            continue
        key, value = raw_line.split('=', 1)
        sections[current][key.strip()] = value.split(';', 1)[0].strip()
    return sections


def _case_insensitive_item(values, wanted_key):
    wanted = str(wanted_key).lower()
    return next(
        (
            (key, value)
            for key, value in values.items()
            if str(key).lower() == wanted
        ),
        (None, None),
    )


def _safe_multiplier(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _format_multiplier(value):
    return f'{float(value):g}'


def _normal_build_time_multipliers_by_category(templates, targets):
    """Derive normal hero/tech timing from comparable ordinary roster units."""
    candidates = {}
    for unit_id, target in targets.items():
        if (
            target.get('special_reward')
            or not target.get('trainable')
            or not target.get('build_limit')
        ):
            continue
        _key, raw_value = _case_insensitive_item(
            templates.get(unit_id.upper(), {}),
            'BuildTimeMultiplier',
        )
        value = _safe_multiplier(raw_value)
        if value is None or value <= 0 or value > MAX_PLAYER_BUILD_TIME_MULTIPLIER:
            continue
        candidates.setdefault(target.get('category'), []).append(value)
    return {
        category: median(values)
        for category, values in candidates.items()
        if category and values
    }


def _normalize_special_reward_build_times(templates, targets):
    """Replace mission-delay multipliers on every producible Special unit."""
    normal_by_category = _normal_build_time_multipliers_by_category(
        templates,
        targets,
    )
    normalized = {}
    for unit_id, target in targets.items():
        if not target.get('special_reward'):
            continue
        template = templates.get(unit_id.upper())
        if not template:
            continue
        for key, raw_value in list(template.items()):
            lowered = str(key).lower()
            if lowered not in BUILD_TIME_MULTIPLIER_KEYS:
                continue
            value = _safe_multiplier(raw_value)
            if (
                value is not None
                and 0 < value <= MAX_PLAYER_BUILD_TIME_MULTIPLIER
            ):
                continue
            replacement = (
                normal_by_category.get(target.get('category'), 1.0)
                if lowered == 'buildtimemultiplier'
                else 1.0
            )
            template[key] = _format_multiplier(replacement)
            normalized.setdefault(unit_id.upper(), {})[key] = template[key]
    return normalized


def _roster_paths_or_raise():
    paths = _active_roster_paths()
    missing_files = [str(path) for path in paths if not path.is_file()]
    if missing_files:
        raise FileNotFoundError(
            'Randomizer unit roster file(s) missing: ' + ', '.join(missing_files)
        )
    return paths


@lru_cache(maxsize=1)
def registered_clone_ids():
    """Return ``{SOURCE_ID: MORP clone id}`` from the committed registry."""
    registry_path = SOURCE_DIR / 'configs' / ROSTER_REGISTRY_FILENAME
    _roster_paths_or_raise()
    list_names = {name.lower() for name in ROSTER_CATEGORIES.values()}
    clone_ids = {}
    for section, values in _read_sections(registry_path).items():
        if section.lower() not in list_names:
            continue
        for clone_id in values.values():
            clone_id = str(clone_id).strip()
            if clone_id.upper().startswith('MORP'):
                clone_ids[clone_id[4:].upper()] = clone_id
    return clone_ids


@lru_cache(maxsize=1)
def map_only_source_sections():
    """Return the reviewed bodies of units no rules file contains."""
    path = SOURCE_DIR / 'configs' / MAP_ONLY_SOURCE_FILENAME
    _roster_paths_or_raise()
    return {
        section.upper(): dict(values)
        for section, values in _read_sections(path).items()
    }


def _installed_sections():
    """Return the installed rules sections, or ``{}`` when unreadable."""
    try:
        from randomizer.ui.cameos import installed_rules_registry

        _superweapons, sections = installed_rules_registry(synchronous=True)
    except Exception:
        # Callers turn an empty registry into a visible failure, but the
        # reason it was empty only exists here.
        from randomizer.core.diagnostics import event as log_event

        log_event(
            'installed_rules_registry_failed',
            traceback=traceback.format_exc(),
        )
        return {}
    return {str(name).upper(): values for name, values in (sections or {}).items()}


@lru_cache(maxsize=1)
def randomizer_unit_template_values():
    """Return each registered clone's body, built from the live rules.

    The reviewed policy applied to the section this installation actually
    loads, with the six map-only bodies filling in for units no rules file
    contains. This is where the shop reads a unit's Cost and TechLevel and
    where the catalogue reads Storage and Harvester, so it has to be the
    clone's own values: six reviewed identities change BuildLimit or Cost
    away from their source, and reading the source would misprice them.

    Called before ``BUFF_TARGETS`` exists -- ``rewards.definitions`` uses it
    while building them -- so category and special-reward status are not
    available here. The one policy branch that needs them normalizes campaign
    build delays, which no caller of this function reads;
    :func:`randomizer_unit_roster` builds the same bodies again with both.

    Scoped to the committed registry rather than every installed section, so
    a caller that iterates this gets the roster and not four thousand weapon
    and warhead definitions.
    """
    from randomizer.config.tuning import CLONE_UI_DESCRIPTION
    from randomizer.rewards.template_policy import (
        build_template_values,
        template_source_id,
    )

    installed = _installed_sections()
    map_only = map_only_source_sections()
    templates = {}
    for source_id in registered_clone_ids():
        wanted = str(template_source_id(source_id)).upper()
        values = installed.get(wanted) or map_only.get(wanted)
        if not values:
            continue
        built = build_template_values(
            source_id,
            values,
            category=None,
            special_reward=False,
            description=CLONE_UI_DESCRIPTION,
        )
        templates[source_id] = dict(built)
    return templates


@lru_cache(maxsize=None)
def randomizer_unit_ids_with_behavior(key, expected_value='yes'):
    """Return source IDs selected by an actual static-template behavior tag."""
    normalized_key = str(key).strip().lower()
    normalized_value = str(expected_value).strip().lower()
    matches = set()
    for source_id, values in randomizer_unit_template_values().items():
        value = next(
            (
                raw_value
                for raw_key, raw_value in values.items()
                if raw_key.strip().lower() == normalized_key
            ),
            None,
        )
        if value is not None and value.strip().lower() == normalized_value:
            matches.add(source_id)
    return frozenset(matches)


@lru_cache(maxsize=1)
def randomizer_unit_roster():
    """Return ``(paths, clone_ids, templates)`` built from the live rules.

    Every clone body is the reviewed policy in ``template_policy`` applied to
    the section the installation loads, so a submodded Rhino and its player
    copy are one unit rather than two sidebar entries with different stats.
    This used to be a committed bake of stock values with the same policy
    replayed over it afterwards at map generation; the bake reproduced from
    the rules exactly, and only the overlay's result ever reached the game.

    Raises rather than returning a thin roster when the rules cannot be read.
    A silent fallback here is a shop full of stock prices and clones that
    disagree with the units beside them, which is the failure this replaced.
    """
    from randomizer.rewards.catalogue import BUFF_TARGETS, SPECIAL_REWARD_UNIT_IDS
    from randomizer.config.tuning import CLONE_UI_DESCRIPTION
    from randomizer.rewards.template_policy import (
        build_template_values,
        template_source_id,
    )

    paths = _roster_paths_or_raise()
    registered = registered_clone_ids()
    installed = _installed_sections()
    map_only = map_only_source_sections()
    if not installed:
        raise FileNotFoundError(
            'Installed rules registry is empty; RULESMO.INI could not be read '
            'from the game directory, and every player clone is built from it.'
        )

    missing = []
    unregistered = []
    templates = {}
    clone_ids = {}
    for source_id, target in BUFF_TARGETS.items():
        # Hidden deploy/undeploy forms are cloned from installed/map rules at
        # launch. They are not independent static roster/access identities.
        if target.get('runtime_transform') or target.get('power_payload_only'):
            continue
        list_name = ROSTER_CATEGORIES.get(target.get('category'))
        if not list_name:
            continue
        source_id = source_id.upper()
        clone_id = registered.get(source_id)
        if not clone_id:
            unregistered.append(f'{source_id}/{list_name}')
            continue
        wanted = str(template_source_id(source_id)).upper()
        source_values = installed.get(wanted) or map_only.get(wanted)
        if not source_values:
            missing.append(f'{source_id}->{wanted}')
            continue
        values = build_template_values(
            source_id,
            source_values,
            category=target.get('category'),
            special_reward=source_id in SPECIAL_REWARD_UNIT_IDS,
            description=CLONE_UI_DESCRIPTION,
        )
        clone_ids[source_id] = clone_id
        templates[source_id] = dict(values)
    if unregistered:
        raise ValueError(
            'Randomizer roster registry lacks required TechnoTypes: '
            + ', '.join(unregistered)
        )
    if missing:
        raise ValueError(
            'No installed or reviewed source section for: ' + ', '.join(missing)
        )
    _normalize_special_reward_build_times(templates, BUFF_TARGETS)
    return paths, clone_ids, templates


def roster_stock_report():
    """Return which rostered units differ from stock Mental Omega rules.

    Building clones from the installed rules is what makes a submod work; it
    is also what makes it invisible. This is the other half: the units whose
    section no longer matches the shipped digest of stock rules, and the ones
    stock has no section for at all.
    """
    from randomizer.core import rules_digest
    from randomizer.rewards.template_policy import template_source_id

    installed = _installed_sections()
    if not installed or not rules_digest.available():
        return {}
    report = {'original': 0, 'modified': [], 'unknown': []}
    for source_id in sorted(registered_clone_ids()):
        wanted = str(template_source_id(source_id)).upper()
        values = installed.get(wanted)
        if values is None:
            # Map-only bodies are not in stock rules by definition; saying so
            # for all six every launch is noise, not information.
            continue
        status = rules_digest.section_status(
            rules_digest.RULES, wanted, values
        )
        if status == rules_digest.ORIGINAL:
            report['original'] += 1
        elif status == rules_digest.MODIFIED:
            report['modified'].append(source_id)
        else:
            report['unknown'].append(source_id)
    return report


def off_stock_unit_ids():
    """Return the rostered units this installation has changed from stock.

    Contracts below are authored against stock Mental Omega, and clone bodies
    come from whatever rules the installation loads. Where those disagree the
    contract is describing a unit that no longer exists on this machine, so it
    is reported rather than raised -- a modded game must still launch.
    """
    report = roster_stock_report()
    return set(report.get('modified', ())) | set(report.get('unknown', ()))


def summarize_roster_stock_report(report, limit=12):
    """Return one log line describing how far the roster is from stock."""
    if not report:
        return (
            'Stock comparison unavailable; player clones still follow the '
            'installed rules.'
        )
    changed = report['modified'] + report['unknown']
    if not changed:
        return (
            f'Player clones follow the installed rules; all '
            f'{report["original"]} rostered units match stock Mental Omega.'
        )
    shown = ', '.join(changed[:limit])
    if len(changed) > limit:
        shown += f', +{len(changed) - limit} more'
    return (
        f'{len(changed)} rostered unit(s) differ from stock Mental Omega and '
        f'their player clones follow the modified rules: {shown}.'
    )


def validate_randomizer_unit_roster():
    paths, clone_ids, templates = randomizer_unit_roster()
    return {
        'paths': [str(path) for path in paths],
        'files': len(paths),
        'types': len(clone_ids),
        'templates': len(templates),
    }


def validate_drakuv_contracts():
    """Keep Drakuv production and aid delivery on one safe identity."""
    from randomizer.rewards.catalogue import (
        AID_POWER_UNLOCK_REWARDS,
        BUFF_TARGETS,
        POWER_BUFF_REWARDS,
        RETIRED_REWARD_BY_NAME,
        REWARD_POOL,
        UNIT_BUFF_REWARDS,
    )
    from randomizer.rewards.power_buff_definitions import power_buff_type_ids

    paths, clone_ids, templates = randomizer_unit_roster()
    clone_id = clone_ids.get('RAVA')
    template = templates.get('RAVA', {})
    _build_key, build_time = _case_insensitive_item(
        template,
        'BuildTimeMultiplier',
    )
    _trainable_key, trainable = _case_insensitive_item(template, 'Trainable')
    _image_key, image = _case_insensitive_item(template, 'Image')
    reward_names = [str(reward.get('name') or '') for reward in REWARD_POOL]
    access_name = 'Drakuv Prison Vehicle Access'
    power_name = 'Drakuv Prison Vehicle Power'
    access_count = reward_names.count(access_name)
    power_count = reward_names.count(power_name)
    duplicate_names = sorted({
        name for name in reward_names
        if name and reward_names.count(name) > 1
    })
    aid_unlock_count = sum(
        1 for reward in AID_POWER_UNLOCK_REWARDS
        if reward.get('superweapon') == 'DrakuvSpecial'
    )
    power_buff_types = tuple(power_buff_type_ids('DrakuvSpecial'))
    drakuv_unit_buff_types = sorted({
        str(reward.get('buff_type') or '')
        for reward in UNIT_BUFF_REWARDS
        if str(reward.get('unit') or '').upper() == 'RAVA'
    })
    drakuv_power_buff_count = sum(
        1 for reward in POWER_BUFF_REWARDS
        if reward.get('superweapon') == 'DrakuvSpecial'
    )
    expected_unit_buffs = {
        'ammo', 'armor', 'cloak', 'cost', 'damage', 'health', 'production',
        'range', 'reload', 'sensors', 'sight', 'speed', 'veteran',
    }
    clone_registrations = sum(
        1
        for path in paths
        for section, values in _read_sections(path).items()
        if section.lower() == 'vehicletypes'
        for value in values.values()
        if str(value).upper() == 'MORPRAVA'
    )
    errors = []
    if clone_id != 'MORPRAVA':
        errors.append(f'RAVA clone is {clone_id!r}, expected MORPRAVA')
    if str(build_time) != '1':
        errors.append(f'MORPRAVA BuildTimeMultiplier is {build_time!r}')
    if str(trainable).lower() != 'yes':
        errors.append(f'MORPRAVA Trainable is {trainable!r}')
    if str(image).upper() != 'RAVA':
        errors.append(f'MORPRAVA Image is {image!r}')
    target = BUFF_TARGETS.get('RAVA', {})
    if target.get('category') != 'units' or not target.get('trainable'):
        errors.append('RAVA is not a trainable vehicle buff target')
    if set(drakuv_unit_buff_types) != expected_unit_buffs:
        errors.append(
            'RAVA unit buffs differ: ' + ','.join(drakuv_unit_buff_types)
        )
    if power_buff_types != ('recharge', 'cost', 'payload'):
        errors.append(f'DrakuvSpecial buffs are {power_buff_types!r}')
    if drakuv_power_buff_count != len(power_buff_types):
        errors.append(
            f'DrakuvSpecial has {drakuv_power_buff_count} buff rewards'
        )
    if access_count != 1 or power_count != 1 or aid_unlock_count != 1:
        errors.append(
            f'Drakuv entries access={access_count}, power={power_count}, '
            f'aid={aid_unlock_count}'
        )
    if clone_registrations != 1:
        errors.append(
            f'MORPRAVA has {clone_registrations} VehicleTypes registrations'
        )
    if access_name in RETIRED_REWARD_BY_NAME:
        errors.append('active Drakuv access also exists as retired reward')
    if duplicate_names:
        errors.append('duplicate reward names: ' + ', '.join(duplicate_names))
    if errors:
        raise ValueError('Drakuv contract validation failed: ' + '; '.join(errors))
    return {
        'clone_id': clone_id,
        'build_time_multiplier': str(build_time),
        'trainable': str(trainable),
        'image': str(image),
        'unit_buff_types': drakuv_unit_buff_types,
        'power_buff_types': list(power_buff_types),
        'access_entries': access_count,
        'power_entries': power_count,
        'clone_registrations': clone_registrations,
        'duplicate_reward_names': duplicate_names,
    }


def validate_unit_buff_application_contracts():
    """Prove every rollable unit buff changes a clone or direct weapon."""
    from randomizer.maps.buff_values import (
        _active_direct_buff_counts,
        apply_unit_buff_value,
        apply_weapon_buff_value,
    )
    from randomizer.maps.weapon_buffs import (
        spawned_missile_range_guard_rules,
    )
    from randomizer.rewards.catalogue import (
        BUFF_TARGETS,
        UNIT_BUFF_REWARDS,
        buff_effect_lines,
        buff_stack_limit,
        linked_buff_variant_ids,
    )
    from randomizer.rewards.display import canonical_reward
    from randomizer.rewards.definitions import SUICIDE_RANGE_EXCLUDED_UNIT_IDS

    _paths, _clone_ids, templates = randomizer_unit_roster()
    # The catalogue is authored against stock Mental Omega, and clone bodies
    # now come from whatever rules the installation loads. On a submod the two
    # legitimately disagree: a unit the mod already moved to the speed ceiling
    # takes no more speed, one it gave OpenTopped cannot be given it again,
    # one whose weapons it replaced is not reachable by a weapon buff. None of
    # that is a fault in the reward definitions, and failing the whole
    # self-check over it would make every modded install unlaunchable.
    #
    # So the contract still binds -- but only for units this installation has
    # not changed. The rest are named in the report instead, which is a more
    # useful thing to know than a crash: these are the rewards that do nothing
    # on this player's game.
    stock_report = roster_stock_report()
    off_stock = off_stock_unit_ids()
    errors = []
    inert_off_stock = []

    def report_failure(unit_id, detail):
        peers = linked_buff_variant_ids(unit_id) or {unit_id}
        if off_stock & {str(peer).upper() for peer in peers}:
            inert_off_stock.append(detail)
        else:
            errors.append(detail)

    counts_by_type = {}
    reward_pairs = {
        (str(reward.get('unit') or '').upper(), reward.get('buff_type'))
        for reward in UNIT_BUFF_REWARDS
    }
    forced_suicide_range_rewards = []
    for unit_id in sorted(SUICIDE_RANGE_EXCLUDED_UNIT_IDS):
        if (unit_id, 'range') in reward_pairs:
            errors.append(f'{unit_id} still offers harmful range')
        legacy = {
            'name': f'Legacy {unit_id} range',
            'kind': 'buff',
            'unit': unit_id,
            'buff_type': 'range',
        }
        if canonical_reward(legacy).get('kind') != 'retired':
            errors.append(f'{unit_id} legacy range remains active')
        forced_suicide_range_rewards.append({
            **legacy,
            '_runtime_canonical': True,
        })
    forced_counts = _active_direct_buff_counts(
        forced_suicide_range_rewards,
        require_unlocked_access=False,
    )
    if forced_counts:
        errors.append(
            'mandatory suicide range exclusions reached map buffs: '
            f'{forced_counts}'
        )

    def direct_weapon_ids(values):
        result = set()
        for key, value in (values or {}).items():
            lowered = str(key).lower()
            direct = lowered in {
                'primary', 'secondary', 'eliteprimary', 'elitesecondary',
            }
            direct = direct or (
                lowered.startswith('weapon')
                and lowered.removeprefix('weapon').isdigit()
            ) or (
                lowered.startswith('eliteweapon')
                and lowered.removeprefix('eliteweapon').isdigit()
            )
            weapon_id = str(value or '').strip()
            if direct and weapon_id.lower() not in {'', 'none', '<none>'}:
                result.add(weapon_id.upper())
        return result

    def normalized(values):
        return {
            str(key).lower(): str(value)
            for key, value in (values or {}).items()
        }

    def dead_from(sequence):
        """Return the first stack after which a buff never changes again.

        A single flat stack is not a dead reward. Self-healing at 90 hit
        points steps 1, 2, 3, 4, 4, 5, 6: stack five rounds onto stack four
        and stack six moves again. Reporting the first repeat -- and stopping
        there -- called that reward dead from stack five when 45 of its 50
        stacks still work. A ceiling is the case that really is dead: once
        speed clamps it never moves again.

        ``sequence[0]`` is the unbuffed value, so a return of 1 means the
        reward does nothing at all.
        """
        for index in range(1, len(sequence)):
            if all(
                later == sequence[index - 1] for later in sequence[index:]
            ):
                return index
        return None

    for reward in UNIT_BUFF_REWARDS:
        unit_id = str(reward.get('unit') or '').upper()
        buff_type = str(reward.get('buff_type') or '')
        target = BUFF_TARGETS.get(unit_id, {})
        counts_by_type[buff_type] = counts_by_type.get(buff_type, 0) + 1
        limit = buff_stack_limit(reward)
        count = max(1, int(limit or 1))
        if not buff_effect_lines(reward, count=count):
            errors.append(f'{unit_id}/{buff_type} has no UI effect text')
            continue

        if buff_type in {'damage', 'range', 'reload'}:
            sequence = [()]
            for stack in range(1, count + 1):
                current = []
                for peer_id in sorted(
                    linked_buff_variant_ids(unit_id) or {unit_id}
                ):
                    peer_target = BUFF_TARGETS.get(peer_id, target)
                    direct_ids = direct_weapon_ids(templates.get(peer_id, {}))
                    if peer_target.get('power_payload_only'):
                        # Installed payload-only identities are cloned from
                        # live rules, not bundled production templates.
                        direct_ids.update(
                            str(weapon_id).upper()
                            for weapon_id in peer_target.get('weapons', {})
                        )
                    for weapon_id, stats in sorted(
                        peer_target.get('weapons', {}).items()
                    ):
                        if str(weapon_id).upper() not in direct_ids:
                            continue
                        changed = {}
                        if apply_weapon_buff_value(
                            changed,
                            stats,
                            buff_type,
                            stack,
                        ):
                            changed_values = normalized(changed)
                            stat_field = (
                                'rof' if buff_type == 'reload' else buff_type
                            )
                            if changed_values.get(stat_field) == str(
                                stats.get(stat_field)
                            ):
                                continue
                            current.append((
                                peer_id,
                                str(weapon_id).upper(),
                                tuple(sorted(changed_values.items())),
                            ))
                    if buff_type == 'range':
                        for missile_id, values in sorted(
                            spawned_missile_range_guard_rules(
                                peer_target, stack
                            ).items()
                        ):
                            current.append((
                                peer_id,
                                str(missile_id).upper(),
                                tuple(sorted(normalized(values).items())),
                            ))
                sequence.append(tuple(current))
            stops = dead_from(sequence)
            if stops is not None:
                report_failure(
                    unit_id,
                    f'{unit_id}/{buff_type} changes no direct weapon field '
                    f'from stack {stops} of {count}',
                )
            continue

        if buff_type == 'veteran':
            template = templates.get(unit_id, {})
            trainable = _case_insensitive_item(template, 'Trainable')[1]
            if (
                target.get('category')
                not in {'infantry', 'units', 'aircraft', 'defenses'}
                or str(trainable or 'yes').lower() in {'no', 'false', '0'}
            ):
                errors.append(f'{unit_id}/veteran is not trainable')
            continue

        if buff_type in {'build_limit', 'building_limit'}:
            if int(target.get('build_limit', 0)) < 1:
                errors.append(f'{unit_id}/{buff_type} has no positive limit')
            continue

        if target.get('global_production') and buff_type == 'production':
            continue
        before = dict(templates.get(unit_id, {}))
        sequence = [normalized(before)]
        unapplied = None
        for stack in range(1, count + 1):
            after = dict(before)
            try:
                applied = apply_unit_buff_value(
                    after,
                    target,
                    buff_type,
                    stack,
                )
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f'{unit_id}/{buff_type} failed: {exc}')
                unapplied = stack
                break
            if not applied:
                unapplied = stack
                break
            sequence.append(normalized(after))
        if unapplied is not None:
            report_failure(
                unit_id,
                f'{unit_id}/{buff_type} stack {unapplied} applies nothing',
            )
            continue
        stops = dead_from(sequence)
        if stops is not None:
            report_failure(
                unit_id,
                f'{unit_id}/{buff_type} changes no clone field from stack '
                f'{stops} of {count}',
            )

    if errors:
        raise ValueError(
            'Unit buff application contract validation failed: '
            + '; '.join(errors)
        )
    # A buff has to add to what the unit is, not to a number remembered from
    # stock rules. Super Thor is the case that proves it without depending on
    # the installation: its body is committed, its reviewed Passengers is 28,
    # and the catalogue says 25 -- so the old arithmetic wrote 26 and took a
    # seat away. The synthetic rows below pin the same rule for the stats
    # whose baseline does come from the installed rules.
    sthor = dict(templates.get('STHOR', {}))
    sthor_target = BUFF_TARGETS.get('STHOR', {})
    apply_unit_buff_value(sthor, sthor_target, 'passenger_capacity', 1)
    probe_target = {'category': 'units', 'strength': 500, 'sight': 5, 'speed': 4}
    health_probe = {'Strength': '1000'}
    apply_unit_buff_value(health_probe, probe_target, 'health', 1)
    sight_probe = {'Sight': '9'}
    apply_unit_buff_value(sight_probe, probe_target, 'sight', 1)
    live_baselines = {
        'sthor_passengers': _case_insensitive_item(
            templates.get('STHOR', {}), 'Passengers'
        )[1],
        'sthor_buffed': _case_insensitive_item(sthor, 'Passengers')[1],
        'health_from_live_strength': health_probe['Strength'],
        'sight_from_live_sight': sight_probe['Sight'],
    }
    if (
        str(live_baselines['sthor_passengers']) != '28'
        or str(live_baselines['sthor_buffed']) != '29'
        or int(health_probe['Strength']) <= 1000
        or str(sight_probe['Sight']) != '10'
    ):
        errors.append(
            'buffs no longer add to a unit its own values: '
            + repr(live_baselines)
        )

    return {
        'rewards': len(UNIT_BUFF_REWARDS),
        'buff_types': counts_by_type,
        'all_change_generated_rules': True,
        'stock_units_checked': stock_report.get('original', 0),
        'inert_off_stock': sorted(inert_off_stock),
        'live_baselines': live_baselines,
        'suicide_range_excluded_ids': sorted(
            SUICIDE_RANGE_EXCLUDED_UNIT_IDS
        ),
    }


def validate_limited_hero_build_limits():
    """Audit capped hero clones and their command-capacity rewards."""
    from randomizer.rewards.definitions import (
        BUFF_TARGETS,
        LIMITED_HERO_BUILD_LIMITS,
        UNIT_BUFF_REWARDS,
    )

    _paths, _clone_ids, templates = randomizer_unit_roster()
    reward_pairs = {
        (str(reward.get('unit', '')).upper(), reward.get('buff_type'))
        for reward in UNIT_BUFF_REWARDS
    }
    errors = []
    for unit_id, expected_limit in LIMITED_HERO_BUILD_LIMITS.items():
        target_limit = BUFF_TARGETS.get(unit_id, {}).get('build_limit')
        _key, template_limit = _case_insensitive_item(
            templates.get(unit_id, {}),
            'BuildLimit',
        )
        if target_limit != expected_limit:
            errors.append(
                f'{unit_id} target limit {target_limit!r} != {expected_limit}'
            )
        if str(template_limit or '') != str(expected_limit):
            errors.append(
                f'{unit_id} clone limit {template_limit!r} != {expected_limit}'
            )
        if (unit_id, 'build_limit') not in reward_pairs:
            errors.append(f'{unit_id} lacks command-capacity reward')
    _key, yuri_prime_cloneable = _case_insensitive_item(
        templates.get('YURIPR', {}), 'Cloneable'
    )
    if str(yuri_prime_cloneable or '').lower() != 'no':
        errors.append('YURIPR must be Cloneable=no to protect its build queue')
    if errors:
        raise ValueError(
            'Limited hero build-limit validation failed: ' + '; '.join(errors)
        )
    return {
        'types': len(LIMITED_HERO_BUILD_LIMITS),
        'unit_ids': sorted(LIMITED_HERO_BUILD_LIMITS),
        'command_capacity_rewards': len(LIMITED_HERO_BUILD_LIMITS),
        'unclonable_limited_ids': ['YURIPR'],
    }


def validate_special_roster_contracts():
    """Audit reviewed campaign-only player production identities."""
    from randomizer.rewards.catalogue import (
        BUFF_TARGETS,
        REWARD_POOL,
        STANDALONE_WEAPON_TEMPLATES,
        UNIT_SIDEBAR_IMAGES,
    )
    from randomizer.rewards.rules import tech_ids_for_rewards

    paths, clone_ids, templates = randomizer_unit_roster()
    errors = []
    registrations = {}
    expected_lists = {
        'CBRIS': 'InfantryTypes',
        'STARDUSTB': 'VehicleTypes',
        'YURIX2': 'InfantryTypes',
    }
    for source_id, list_name in expected_lists.items():
        clone_id = clone_ids.get(source_id)
        matches = []
        for path in paths:
            sections = _read_sections(path)
            actual_list = next(
                (
                    section
                    for section in sections
                    if section.lower() == list_name.lower()
                ),
                None,
            )
            if not actual_list:
                continue
            matches.extend(
                (path.name, str(key))
                for key, value in sections[actual_list].items()
                if str(value).upper() == str(clone_id or '').upper()
            )
        # Packaged installs preserve editable visible rosters. When an older
        # visible file lacks a newly bundled identity, randomizer_unit_roster()
        # correctly supplies its registration/template from bundled data.
        # Audit that effective fallback instead of reporting a false failure.
        if not matches and FROZEN:
            for name in ROSTER_FILENAMES:
                bundled_path = SOURCE_DIR / 'configs' / name
                if not bundled_path.is_file():
                    continue
                sections = _read_sections(bundled_path)
                actual_list = next(
                    (
                        section for section in sections
                        if section.lower() == list_name.lower()
                    ),
                    None,
                )
                matches.extend(
                    (f'bundled:{bundled_path.name}', str(key))
                    for key, value in sections.get(actual_list, {}).items()
                    if str(value).upper() == str(clone_id or '').upper()
                )
        registrations[source_id] = matches
        if len(matches) != 1:
            errors.append(
                f'{source_id} has {len(matches)} {list_name} registrations'
            )

    boomer_reward_count = sum(
        1
        for reward in REWARD_POOL
        if (
            str(reward.get('unit', '')).upper() == 'BRUTE2'
            or 'BRUTE2' in tech_ids_for_rewards([reward])
        )
    )
    boomer_excluded = bool(
        'BRUTE2' not in clone_ids
        and 'BRUTE2' not in templates
        and 'BRUTE2' not in BUFF_TARGETS
        and boomer_reward_count == 0
    )
    if not boomer_excluded:
        errors.append(
            'BRUTE2 remains in player roster/rewards '
            f'(reward_count={boomer_reward_count})'
        )

    commando = templates.get('CBRIS', {})
    _key, theater_gate = _case_insensitive_item(
        commando, 'Prerequisite.RequiredTheaters'
    )
    if str(theater_gate or '').strip().lower() not in {'', 'none', '<none>'}:
        errors.append(f'CBRIS retains theater gate {theater_gate!r}')

    paradox = templates.get('STARDUSTB', {})
    paradox_required = {
        'Image': 'STARDUST',
        'Name': 'The Paradox Engine',
        'BuildLimit': '1',
        'BuildTimeMultiplier': '1',
        'IsGattling': 'yes',
        'Turret': 'no',
        'TurretCount': '1',
        'CanPassiveAquire': 'yes',
        'CanRetaliate': 'yes',
        'WeaponCount': '6',
        'WeaponStages': '3',
        'Stage1': '40',
        'Stage2': '80',
        'Stage3': '120',
        'RateUp': '5',
        'RateDown': '10',
        'OpportunityFire': 'yes',
        'PreventAttackMove': 'no',
        'HoverAttack': 'yes',
        'Locomotor': '{92612C46-F71F-11d1-AC9F-006008055BB5}',
        'MovementZone': 'Fly',
        **{
            f'{prefix}Weapon{number}': (
                'ParadoxMedusa' if number % 2 == 0 else 'ParadoxPrism'
            )
            for prefix in ('', 'Elite')
            for number in range(1, 7)
        },
    }
    for key, expected in paradox_required.items():
        _actual_key, actual = _case_insensitive_item(paradox, key)
        if str(actual or '').lower() != expected.lower():
            errors.append(f'STARDUSTB.{key}={actual!r}')
    ammo_key, ammo_value = _case_insensitive_item(paradox, 'Ammo')
    if ammo_key is not None and str(ammo_value).strip() not in {'', '-1'}:
        errors.append(f'STARDUSTB.Ammo={ammo_value!r}')
    paradox_target = BUFF_TARGETS.get('STARDUSTB', {})
    if (
        paradox_target.get('category') != 'units'
        or paradox_target.get('factions') != ['Allies']
        or not paradox_target.get('special_reward')
        or paradox_target.get('build_limit') != 1
    ):
        errors.append(f'STARDUSTB target metadata={paradox_target!r}')
    if 'STARDUST' in clone_ids:
        errors.append('AI-only STARDUST has a player clone')

    yuri = templates.get('YURIX2', {})
    yuri_required = {
        'Name': 'Yuri',
        'UIName': 'Name:YURIHIMSELF',
        'Image': 'YURIX',
        'Strength': '400',
        'Armor': 'sieg',
        'Speed': '7',
        'Cost': '1500',
        'PixelSelectionBracketDelta': '-24',
        'Experience.MindControlSelfModifier': '100%',
        'ImmuneToEMP': 'no',
        'Primary': 'SuperMindControl',
        'Secondary': 'SuperPsiWave',
        'BuildLimit': '1',
        'BuildTimeMultiplier': '2',
    }
    for key, expected in yuri_required.items():
        _actual_key, actual = _case_insensitive_item(yuri, key)
        if str(actual or '').lower() != expected.lower():
            errors.append(f'YURIX2.{key}={actual!r}')
    yuri_target = BUFF_TARGETS.get('YURIX2', {})
    if (
        yuri_target.get('category') != 'infantry'
        or yuri_target.get('factions') != ['Epsilon']
        or not yuri_target.get('special_reward')
        or yuri_target.get('build_limit') != 1
        or yuri_target.get('cost') != 1500
        or yuri_target.get('speed') != 7
        or yuri_target.get('strength') != 400
        or yuri_target.get('guard_range') != 8
        or yuri_target.get('weapons') != {
            'SuperMindControl': {
                'damage': 1, 'rof': 100, 'range': 10,
            },
            'SuperPsiWave': {
                'damage': 300, 'rof': 50, 'range': 1,
            },
        }
    ):
        errors.append(f'YURIX2 target metadata={yuri_target!r}')
    yuri_cameo = UNIT_SIDEBAR_IMAGES.get('YURIX2', {})
    if yuri_cameo != {'source_pcx': 'yuriicon.pcx', 'art_id': 'YURIX'}:
        errors.append(f'YURIX2 cameo mapping={yuri_cameo!r}')
    for key in (
        'AttachEffect.Animation', 'AttachEffect.Duration',
        'ImmuneToPsionicWeapons', 'OpenTransportWeapon',
    ):
        _actual_key, actual = _case_insensitive_item(yuri, key)
        if str(actual or '').strip().lower() not in {'', 'none', '<none>'}:
            errors.append(f'YURIX2.{key}={actual!r}')
    if 'MORYURIPRIMECONTROL' in STANDALONE_WEAPON_TEMPLATES:
        errors.append('Obsolete Death\'s Hand Yuri weapon template remains')

    cameo = UNIT_SIDEBAR_IMAGES.get('STARDUSTB', {})
    if cameo != {
        'image': 'paradox_engine.png',
        'pcx': 'morparadoxicon.pcx',
        'art_id': 'STARDUST',
    }:
        errors.append(f'STARDUSTB cameo mapping={cameo!r}')
    cameo_path = SOURCE_DIR / 'assets' / 'paradox_engine.png'
    if not cameo_path.is_file():
        errors.append('Paradox Engine cameo asset is missing')

    access_counts = {}
    for source_id in expected_lists:
        access_counts[source_id] = sum(
            1
            for reward in REWARD_POOL
            if reward.get('kind') != 'buff'
            and source_id in tech_ids_for_rewards([reward])
        )
        if access_counts[source_id] != 1:
            errors.append(
                f'{source_id} has {access_counts[source_id]} access rewards'
            )
    yuri_access_rewards = [
        reward
        for reward in REWARD_POOL
        if 'YURIX2' in tech_ids_for_rewards([reward])
    ]
    if any(
        {'YURI', 'YURIPR'}.intersection(tech_ids_for_rewards([reward]))
        for reward in yuri_access_rewards
    ):
        errors.append('YURIX2 access also unlocks a normal Yuri identity')
    if any(
        'STARDUST' in tech_ids_for_rewards([reward])
        for reward in REWARD_POOL
    ):
        errors.append('AI-only STARDUST appears in reward rules')

    if errors:
        raise ValueError(
            'Special roster contract validation failed: ' + '; '.join(errors)
        )
    return {
        'clone_ids': {
            source_id: clone_ids[source_id]
            for source_id in expected_lists
        },
        'registrations': registrations,
        'access_counts': access_counts,
        'space_commando_theater_gate_removed': True,
        'boomer_brute_excluded': boomer_excluded,
        'paradox_source_id': 'STARDUSTB',
        'paradox_ai_alias_excluded': True,
        'paradox_cameo': cameo,
        'special_yuri_source_id': 'YURIX2',
        'special_yuri_cameo': yuri_cameo,
    }


def validate_hidden_passenger_payloads():
    """Audit portable weapon-passenger payloads and hidden UI controls."""
    _paths, clone_ids, templates = randomizer_unit_roster()
    expected = {
        'STHOR': {
            'sources': ('GGI', 'ENFO', 'HCRUIS'),
            'counts': (5, 5, 1),
            'capacity': 28,
            'size_limit': 18,
            'weapons': {
                'STHOR': {
                    'Primary': 'ThorHeavyGun',
                    'ElitePrimary': 'ThorHeavyGun',
                },
                'GGI': {
                    'Primary': 'MissileLauncher',
                    'ElitePrimary': 'MissileLauncherE',
                    'Secondary': 'MissileLauncherDep',
                    'EliteSecondary': 'MissileLauncherDepE',
                    'OpenTransportWeapon': '1',
                },
                'ENFO': {
                    'Primary': 'EnforcerGun',
                    'ElitePrimary': 'EnforcerGunE',
                    'Secondary': 'EnforcerGun2',
                    'EliteSecondary': 'EnforcerGun2E',
                    'OpenTransportWeapon': '1',
                },
                'HCRUIS': {
                    'Primary': 'CruiserCannonA',
                    'ElitePrimary': 'CruiserCannonAE',
                    'Secondary': 'CruiserCannonB',
                    'EliteSecondary': 'CruiserCannonBE',
                },
            },
        },
        'SALA': {
            'sources': ('SALA_1', 'SALA_2'),
            'counts': (3, 1),
            'capacity': 4,
            'size_limit': 1,
            'weapons': {
                'SALA': {
                    'Weapon1': 'SalamanderBow',
                    'EliteWeapon1': 'SalamanderBow',
                    'Weapon2': 'SalamanderBowAA',
                    'EliteWeapon2': 'SalamanderBowAA',
                    'Weapon3': 'SalamanderBow',
                    'EliteWeapon3': 'SalamanderBow',
                    'Weapon4': 'SalamanderBowAA',
                    'EliteWeapon4': 'SalamanderBowAA',
                },
                'SALA_1': {
                    'Primary': 'SalamanderBeam',
                    'Secondary': 'SalamanderBeamAA',
                },
                'SALA_2': {
                    'Primary': 'SalamanderField',
                },
            },
        },
    }
    errors = []
    report = {}
    for carrier_id, contract in expected.items():
        carrier = templates.get(carrier_id, {})
        payload_ids = tuple(
            item.strip().upper()
            for item in str(_case_insensitive_item(
                carrier, 'InitialPayload.Types'
            )[1] or '').split(',')
            if item.strip()
        )
        allowed_ids = tuple(
            item.strip().upper()
            for item in str(_case_insensitive_item(
                carrier, 'Passengers.Allowed'
            )[1] or '').split(',')
            if item.strip()
        )
        payload_counts = tuple(
            int(item.strip())
            for item in str(_case_insensitive_item(
                carrier, 'InitialPayload.Nums'
            )[1] or '').split(',')
            if item.strip()
        )
        expected_ids = tuple(
            clone_ids[source_id] for source_id in contract['sources']
        )
        if payload_ids != expected_ids or allowed_ids != expected_ids:
            errors.append(f'{carrier_id} payload/allowed types differ')
        if payload_counts != contract['counts']:
            errors.append(f'{carrier_id} payload counts differ')
        required_carrier_values = {
            'Passengers': str(contract['capacity']),
            'SizeLimit': str(contract['size_limit']),
            'PipScale': 'none',
            'OpenTopped': 'yes',
            'NoManualEnter': 'yes',
            'NoManualUnload': 'yes',
            'Survivor.RookiePassengerChance': '0%',
            'Survivor.VeteranPassengerChance': '0%',
            'Survivor.ElitePassengerChance': '0%',
        }
        for key, wanted in required_carrier_values.items():
            _actual_key, actual = _case_insensitive_item(carrier, key)
            if str(actual or '').lower() != wanted.lower():
                errors.append(f'{carrier_id}.{key}={actual!r}')
        payload_size = 0
        for source_id, count in zip(contract['sources'], contract['counts']):
            _size_key, raw_size = _case_insensitive_item(
                templates.get(source_id, {}), 'Size'
            )
            try:
                payload_size += int(raw_size) * count
            except (TypeError, ValueError):
                errors.append(f'{source_id}.Size={raw_size!r}')
        if payload_size != contract['capacity']:
            errors.append(
                f'{carrier_id} payload size {payload_size} != '
                f'{contract["capacity"]}'
            )
        for source_id, weapon_values in contract['weapons'].items():
            template = templates.get(source_id, {})
            for key, wanted in weapon_values.items():
                _actual_key, actual = _case_insensitive_item(template, key)
                if str(actual or '') != wanted:
                    errors.append(f'{source_id}.{key}={actual!r}')
        report[carrier_id] = {
            'payload_types': list(payload_ids),
            'payload_counts': list(payload_counts),
            'payload_size': payload_size,
            'capacity': contract['capacity'],
        }
    thor = templates.get('STHOR', {})
    _marker_key, marker = _case_insensitive_item(
        thor, 'AttachEffect.Animation'
    )
    if str(marker or '').strip().lower() not in {'', 'none', '<none>'}:
        errors.append(f'STHOR.AttachEffect.Animation={marker!r}')
    if errors:
        raise ValueError(
            'Hidden passenger payload validation failed: '
            + '; '.join(errors)
        )
    return report


def validate_reviewed_vehicle_identity_contracts():
    """Audit reviewed special identities and passenger-free vehicle contracts."""
    from randomizer.rewards.catalogue import (
        BUFF_TARGETS,
        REWARD_POOL,
        UNIT_SIDEBAR_IMAGES,
    )
    from randomizer.rewards.definitions import UNIT_BUFF_REWARDS
    from randomizer.rewards.display import canonical_reward
    from randomizer.rewards.rules import tech_ids_for_rewards
    from randomizer.maps.buff_values import _active_direct_buff_counts

    _paths, clone_ids, templates = randomizer_unit_roster()
    errors = []
    expected_identity = {
        'TENGU': {
            'clone': 'MORPTENGU',
            'name': 'Tsurugi Powersuit',
            'ui_name': 'NAME:TENGU',
            'image': 'TENGU',
            'cameo': 'tsuricon.pcx',
            'special': False,
        },
        'MECHA': {
            'clone': 'MORPMECHA',
            'name': 'Robo Tengu',
            'ui_name': 'NAME:MECHA',
            'image': 'MECHA',
            'cameo': 'tengu.pcx',
            'special': True,
        },
        'RAMW': {
            'clone': 'MORPRAMW',
            'name': 'Ramwagon',
            'ui_name': 'NAME:RAMW',
            'image': 'RAMW',
            'cameo': None,
            'special': True,
        },
        'OTRK': {
            'clone': 'MORPOTRK',
            'name': 'Old Demo Truck',
            'ui_name': 'NOSTR:Old Demo Truck',
            'image': 'OTRK',
            'cameo': 'otrk.pcx',
            'special': True,
        },
    }
    identity_report = {}
    for source_id, expected in expected_identity.items():
        template = templates.get(source_id, {})
        actual = {
            'clone': clone_ids.get(source_id),
            'name': _case_insensitive_item(template, 'Name')[1],
            'ui_name': _case_insensitive_item(template, 'UIName')[1],
            'image': _case_insensitive_item(template, 'Image')[1],
            'cameo': UNIT_SIDEBAR_IMAGES.get(source_id, {}).get('source_pcx'),
            'special': bool(
                BUFF_TARGETS.get(source_id, {}).get('special_reward')
            ),
        }
        identity_report[source_id] = actual
        for key, wanted in expected.items():
            if str(actual.get(key)).lower() != str(wanted).lower():
                errors.append(f'{source_id}.{key}={actual.get(key)!r}')
        access_count = sum(
            1
            for reward in REWARD_POOL
            if reward.get('kind') != 'buff'
            and source_id in tech_ids_for_rewards([reward])
        )
        if access_count != 1:
            errors.append(f'{source_id} has {access_count} access rewards')
    if clone_ids.get('TENGU') == clone_ids.get('MECHA'):
        errors.append('TENGU and MECHA share one player clone ID')
    dtruck_ui_name = _case_insensitive_item(
        templates.get('DTRUCK', {}), 'UIName'
    )[1]
    otrk_ui_name = _case_insensitive_item(
        templates.get('OTRK', {}), 'UIName'
    )[1]
    if str(dtruck_ui_name or '').lower() == str(otrk_ui_name or '').lower():
        errors.append('DTRUCK and OTRK share one sidebar UIName')

    ramwagon = templates.get('RAMW', {})
    for key, wanted in {
        'Primary': 'RamWeldCutter',
        'ElitePrimary': 'RamWeldCutter',
        'Secondary': 'RamHackArena',
        'EliteSecondary': 'RamHackArena',
        'Ammo': '4',
        'SelfHealing': 'yes',
    }.items():
        actual = _case_insensitive_item(ramwagon, key)[1]
        if str(actual or '').lower() != wanted.lower():
            errors.append(f'RAMW.{key}={actual!r}')
    ramwagon_weapons = BUFF_TARGETS.get('RAMW', {}).get('weapons', {})
    if ramwagon_weapons != {
        'RamWeldCutter': {'damage': 12, 'range': 7},
    }:
        errors.append(f'RAMW buff weapons={ramwagon_weapons!r}')
    if any(
        str(reward.get('unit', '')).upper() == 'RAMW'
        and reward.get('buff_type') == 'self_healing'
        for reward in UNIT_BUFF_REWARDS
    ):
        errors.append('RAMW offers redundant self-healing buff')

    chrp = templates.get('CHRP', {})
    chrp_required = {
        'Image': 'CHRP',
        'Strength': '950',
        'Armor': 'prison',
        'Locomotor': '{4A582741-9839-11d1-B709-00A024DDAFD1}',
        'MovementZone': 'Normal',
        'Speed': '4',
        'Turret': 'yes',
        'TurretCount': '2',
        'PipScale': 'Passengers',
        'PassengerTurret': 'yes',
        'Passengers': '3',
        'Passengers.BySize': 'no',
        'SizeLimit': '9',
        'NoManualEnter': 'yes',
        'Survivor.RookiePassengerChance': '100%',
        'Survivor.VeteranPassengerChance': '100%',
        'Survivor.ElitePassengerChance': '100%',
        'EnterTransportSound': 'EnterTransport',
        'LeaveTransportSound': 'ExitTransport',
        'Primary': 'ChronoImprison',
        'Weapon1': 'ChronoImprison',
    }
    for key, wanted in chrp_required.items():
        actual = _case_insensitive_item(chrp, key)[1]
        if str(actual or '').lower() != wanted.lower():
            errors.append(f'CHRP.{key}={actual!r}')
    for key in ('NoManualUnload',):
        actual_key, actual = _case_insensitive_item(chrp, key)
        if actual_key is not None and actual not in {None, ''}:
            errors.append(f'CHRP.{key}={actual!r}')

    abrm = templates.get('ABRM', {})
    for key in (
        'Passengers',
        'Passengers.BySize',
        'SizeLimit',
        'OpenTopped',
        'Gunner',
        'EnterTransportSound',
        'LeaveTransportSound',
    ):
        actual_key, actual = _case_insensitive_item(abrm, key)
        if actual_key is not None and str(actual or '').lower() not in {
            '', '0', 'no',
        }:
            errors.append(f'ABRM.{key}={actual!r}')
    if str(_case_insensitive_item(abrm, 'PipScale')[1]).lower() != 'none':
        errors.append('ABRM.PipScale is not none')

    forbidden_transport_rewards = {
        (str(reward.get('unit', '')).upper(), reward.get('buff_type'))
        for reward in UNIT_BUFF_REWARDS
        if str(reward.get('unit', '')).upper() == 'CHRP'
        and reward.get('buff_type') in {'passenger_capacity', 'open_topped'}
    }
    if forbidden_transport_rewards:
        errors.append(
            f'CHRP still offers transport buffs {forbidden_transport_rewards}'
        )
    forced_transport_rewards = []
    for buff_type in ('passenger_capacity', 'open_topped'):
        legacy = {
            'name': f'Legacy CHRP {buff_type}',
            'kind': 'buff',
            'unit': 'CHRP',
            'buff_type': buff_type,
        }
        if canonical_reward(legacy).get('kind') != 'retired':
            errors.append(f'CHRP legacy {buff_type} remains active')
        forced_transport_rewards.append({
            **legacy,
            '_runtime_canonical': True,
        })
    forced_counts = _active_direct_buff_counts(
        forced_transport_rewards,
        require_unlocked_access=False,
    )
    if forced_counts:
        errors.append(f'CHRP forced transport buffs reached maps: {forced_counts}')
    if errors:
        raise ValueError(
            'Reviewed vehicle identity validation failed: ' + '; '.join(errors)
        )
    return {
        'identities': identity_report,
        'chrono_prison_capture_release_contract': True,
        'abrams_matches_passenger_free_original': True,
    }


def validate_randomizer_unit_health():
    """Audit the authoritative player templates used by every spawn path."""
    from randomizer.rewards.catalogue import (
        BUFF_TARGETS,
        LINKED_ACCESS_VARIANTS,
        LINKED_BUFF_VARIANTS,
        SPECIAL_REWARD_UNIT_IDS,
    )

    _paths, clone_ids, templates = randomizer_unit_roster()
    errors = []
    strengths = {}
    for source_id in sorted(clone_ids):
        key, raw_value = _case_insensitive_item(
            templates.get(source_id, {}),
            'Strength',
        )
        value = _safe_multiplier(raw_value)
        if (
            key is None
            or value is None
            or value < 2
            or value != round(value)
        ):
            errors.append(f'{source_id} has unsafe Strength={raw_value!r}')
            continue
        strengths[source_id] = int(value)
    hand_contracts = {}
    right_hand_player_links = bool(
        'DHANDR' in clone_ids
        or 'DHANDR' in BUFF_TARGETS
        or 'DHANDR' in SPECIAL_REWARD_UNIT_IDS
        or any('DHANDR' in variants for variants in LINKED_ACCESS_VARIANTS.values())
        or any('DHANDR' in variants for variants in LINKED_BUFF_VARIANTS.values())
    )
    if right_hand_player_links:
        errors.append('Duplicate right Hand of Ereshkigal player clone remains')
    for source_id in ('DHANDL',):
        template = templates.get(source_id, {})
        _strength_key, raw_strength = _case_insensitive_item(
            template,
            'Strength',
        )
        _armor_key, raw_armor = _case_insensitive_item(template, 'Armor')
        _bracket_key, raw_bracket = _case_insensitive_item(
            template,
            'PixelSelectionBracketDelta',
        )
        strength = _safe_multiplier(raw_strength)
        bracket = _safe_multiplier(raw_bracket)
        values = {
            str(key).lower(): str(value)
            for key, value in template.items()
            if value is not None
        }
        expected_speed = '9'
        weapons_preserved = all(
            values.get(f'{prefix}weapon{number}')
            == ('DeathBoltAA' if number % 2 == 0 else 'DeathBolt')
            for prefix in ('', 'elite')
            for number in range(1, 11)
        )
        visible_health_bar = bool(
            bracket is not None and abs(bracket) < 100
        )
        normal_damage_and_death = bool(
            strength is not None
            and strength >= 2
            and values.get('armor', '').lower() == 'f_heroic'
            and values.get('isselectablecombatant', '').lower() == 'yes'
            and values.get('crashable', '').lower() == 'yes'
            and values.get('deathweapon') == 'BlimpBombEffect'
            and bool(values.get('explosion'))
        )
        behavior_preserved = bool(
            weapons_preserved
            and values.get('image') == source_id
            and values.get('speed') == expected_speed
            and values.get('jumpjetspeed') == expected_speed
            and values.get('movementzone', '').lower() == 'fly'
            and values.get('attacheffect.animation') == 'DRING'
        )
        contract = {
            'strength': int(strength) if strength is not None else None,
            'armor': str(raw_armor or ''),
            'pixel_selection_bracket_delta': (
                int(bracket) if bracket is not None else None
            ),
            'visible_health_bar': visible_health_bar,
            'normal_damage_and_death': normal_damage_and_death,
            'weapons_movement_art_preserved': behavior_preserved,
        }
        hand_contracts[source_id] = contract
        if not all((
            visible_health_bar,
            normal_damage_and_death,
            behavior_preserved,
        )):
            detail = (
                f'{source_id} player health contract invalid: '
                f'Strength={raw_strength!r}, Armor={raw_armor!r}, '
                f'PixelSelectionBracketDelta={raw_bracket!r}'
            )
            # This describes stock Mental Omega's Hand of Ereshkigal. A submod
            # that retunes it -- this machine's raises JumpJetSpeed from 9 to
            # 15 -- has not broken the launcher.
            if source_id in off_stock_unit_ids():
                contract['off_stock'] = True
            else:
                errors.append(detail)
    if errors:
        raise ValueError(
            'Randomizer player-template health validation failed: '
            + '; '.join(errors)
        )
    return {
        'types': len(strengths),
        'minimum_strength': min(strengths.values(), default=0),
        'maximum_strength': max(strengths.values(), default=0),
        'hands_of_ereshkigal': hand_contracts,
        'right_hand_native_only': not right_hand_player_links,
    }


def validate_special_reward_build_times():
    """Audit every producible campaign/Special template for sane timing."""
    from randomizer.rewards.catalogue import BUFF_TARGETS

    _paths, _clone_ids, templates = randomizer_unit_roster()
    special_ids = sorted(
        unit_id.upper()
        for unit_id, target in BUFF_TARGETS.items()
        if target.get('special_reward')
        and not target.get('runtime_transform')
        and not target.get('power_payload_only')
        and target.get('category') in ROSTER_CATEGORIES
    )
    errors = []
    effective = {}
    for unit_id in special_ids:
        template = templates.get(unit_id)
        if not template:
            errors.append(f'{unit_id} has no player template')
            continue
        for key, raw_value in template.items():
            lowered = str(key).lower()
            if lowered not in BUILD_TIME_MULTIPLIER_KEYS:
                continue
            value = _safe_multiplier(raw_value)
            if (
                value is None
                or value <= 0
                or value > MAX_PLAYER_BUILD_TIME_MULTIPLIER
            ):
                errors.append(f'{unit_id} has unusable {key}={raw_value}')
                continue
        build_time_key, build_time_raw = _case_insensitive_item(
            template,
            'BuildTimeMultiplier',
        )
        effective[unit_id] = (
            _safe_multiplier(build_time_raw)
            if build_time_key is not None
            else 1.0
        )
    if errors:
        raise ValueError(
            'Special reward build-time validation failed: ' + '; '.join(errors)
        )
    return {
        'types': len(special_ids),
        'unit_ids': special_ids,
        'max_effective_multiplier': max(effective.values(), default=1.0),
        'effective_multipliers': effective,
    }


def validate_transport_buff_eligibility():
    """Audit IFV/OpenTopped reward invariants used by every selection UI."""
    from randomizer.maps.buff_values import _active_direct_buff_counts
    from randomizer.rewards.display import canonical_reward
    from randomizer.rewards.definitions import (
        ENGINEER_UNIT_IDS,
        EXISTING_OPEN_TOPPED_IDS,
        TRANSPORT_GUNNER_IDS,
        TRANSPORT_OPEN_TOPPED_BLOCKED_IDS,
        UNIT_BUFF_REWARDS,
    )

    _paths, _clone_ids, templates = randomizer_unit_roster()
    template_gunners = randomizer_unit_ids_with_behavior('Gunner', 'yes')
    hidden_weapon_passenger_ids = frozenset({'SALA', 'STHOR'})
    reward_pairs = {
        (str(reward.get('unit', '')).upper(), reward.get('buff_type'))
        for reward in UNIT_BUFF_REWARDS
    }
    forced_runtime_rewards = [
        {
            '_runtime_canonical': True,
            'name': f'Forced {unit_id} {buff_type}',
            'kind': 'buff',
            'unit': unit_id,
            'buff_type': buff_type,
        }
        for unit_id in template_gunners
        for buff_type in ('passenger_capacity', 'open_topped')
    ] + [
        {
            '_runtime_canonical': True,
            'name': f'Forced {unit_id} passenger_capacity',
            'kind': 'buff',
            'unit': unit_id,
            'buff_type': 'passenger_capacity',
        }
        for unit_id in hidden_weapon_passenger_ids
    ] + [{
        '_runtime_canonical': True,
        'name': 'Forced Stallion open_topped',
        'kind': 'buff',
        'unit': 'SHAD',
        'buff_type': 'open_topped',
    }]
    forced_counts = _active_direct_buff_counts(
        forced_runtime_rewards,
        require_unlocked_access=False,
    )
    errors = []
    if forced_counts:
        errors.append(
            f'mandatory transport exclusions reached map buffs: {forced_counts}'
        )
    if template_gunners != TRANSPORT_GUNNER_IDS:
        errors.append(
            'Gunner=yes templates differ from transport-gunner exclusions'
        )
    for unit_id in template_gunners:
        for buff_type in ('passenger_capacity', 'open_topped'):
            if (unit_id, buff_type) in reward_pairs:
                errors.append(f'{unit_id} still offers {buff_type}')
            legacy = canonical_reward({
                'name': f'Legacy {unit_id} {buff_type}',
                'kind': 'buff',
                'unit': unit_id,
                'buff_type': buff_type,
            })
            if legacy.get('kind') != 'retired':
                errors.append(f'{unit_id} legacy {buff_type} remains active')
    for unit_id in hidden_weapon_passenger_ids:
        if (unit_id, 'passenger_capacity') in reward_pairs:
            errors.append(f'{unit_id} still offers passenger_capacity')
        legacy = canonical_reward({
            'name': f'Legacy {unit_id} Passenger Capacity I',
            'kind': 'buff',
            'unit': unit_id,
            'buff_type': 'passenger_capacity',
        })
        if legacy.get('kind') != 'retired':
            errors.append(
                f'{unit_id} legacy passenger_capacity remains active'
            )
    if ('SHAD', 'passenger_capacity') not in reward_pairs:
        errors.append('Stallion lost passenger_capacity')
    if ('SHAD', 'open_topped') in reward_pairs:
        errors.append('Stallion still offers broken open_topped')
    legacy_stallion_open_top = canonical_reward({
        'name': 'Legacy Stallion Passenger Firing I',
        'kind': 'buff',
        'unit': 'SHAD',
        'buff_type': 'open_topped',
    })
    if legacy_stallion_open_top.get('kind') != 'retired':
        errors.append('Stallion legacy open_topped remains active')
    if 'SHAD' not in TRANSPORT_OPEN_TOPPED_BLOCKED_IDS:
        errors.append('Stallion is absent from mandatory OpenTopped exclusions')
    engineer_identity = {
        'Engineer': 'yes',
        'CanDrive': 'yes',
        'GroupAs': 'Engineers',
        'IFVMode': '1',
        'PhysicalSize': '1',
        'Size': '1',
        'Primary': 'DefuseKit',
        'Secondary': 'EngineerScanner',
        'Locomotor': '{4A582744-9839-11d1-B709-00A024DDAFD1}',
        'MovementZone': 'Infantry',
    }
    for unit_id in sorted(ENGINEER_UNIT_IDS):
        template = templates.get(unit_id, {})
        for key, expected in engineer_identity.items():
            _actual_key, actual = _case_insensitive_item(template, key)
            if str(actual or '').lower() != expected.lower():
                errors.append(
                    f'{unit_id} clone lost {key}={expected}'
                )
    if ('HTNK', 'ammo') in reward_pairs:
        errors.append('Rhino still offers harmful ammo capacity')
    legacy_rhino_ammo = canonical_reward({
        'name': 'Rhino Heavy Tank Ammo Reserves I',
        'kind': 'buff',
        'unit': 'HTNK',
        'buff_type': 'ammo',
    })
    if (
        legacy_rhino_ammo.get('unit') != 'HTNK'
        or legacy_rhino_ammo.get('buff_type') != 'reload'
    ):
        errors.append('Legacy Rhino ammo does not migrate to weapon tuning')
    for unit_id in EXISTING_OPEN_TOPPED_IDS:
        template = templates.get(unit_id, {})
        open_topped = next(
            (
                value
                for key, value in template.items()
                if key.strip().lower() == 'opentopped'
            ),
            '',
        )
        if str(open_topped).strip().lower() != 'yes':
            errors.append(f'{unit_id} native OpenTopped=yes was not preserved')
        if (unit_id, 'open_topped') in reward_pairs:
            errors.append(f'{unit_id} offers redundant open_topped')
    if errors:
        raise ValueError('Transport buff eligibility failed: ' + '; '.join(errors))
    return {
        'gunner_ids': sorted(template_gunners),
        'hidden_weapon_passenger_capacity_excluded': sorted(
            hidden_weapon_passenger_ids
        ),
        'stallion_capacity_enabled': True,
        'stallion_open_topped_excluded': True,
        'native_open_topped_ids': sorted(EXISTING_OPEN_TOPPED_IDS),
        'engineer_clone_identity_ids': sorted(ENGINEER_UNIT_IDS),
        'rhino_ammo_migrated_to_reload': True,
    }


def validate_house_wide_buff_policy():
    """Audit that only All Production expands beyond one unit identity."""
    from randomizer.maps.assistance import stacked_house_buff_values
    from randomizer.maps.buff_values import _active_direct_buff_counts
    from randomizer.rewards.definitions import (
        UNIT_BUFF_REWARDS,
        linked_buff_variant_ids,
    )
    from randomizer.rewards.display import house_wide_buff_scope

    forbidden_house_types = {'armor', 'health', 'damage', 'cost'}
    scopes = []
    representatives = {}
    global_production_reward = None
    for reward in UNIT_BUFF_REWARDS:
        scope = house_wide_buff_scope(reward)
        if scope:
            scopes.append((reward, scope))
        buff_type = reward.get('buff_type')
        if (
            buff_type in forbidden_house_types | {'production'}
            and not reward.get('global_buff')
        ):
            representatives.setdefault(buff_type, reward)
        if scope == ('All', 'production'):
            global_production_reward = reward

    errors = []
    scope_set = {scope for _reward, scope in scopes}
    if scope_set != {('All', 'production')}:
        errors.append(f'unexpected house-wide scopes: {sorted(scope_set)}')
    if not global_production_reward:
        errors.append('All Production reward is absent')
    if any(
        reward.get('buff_type') in forbidden_house_types
        for reward, _scope in scopes
    ):
        errors.append('redundant stat/cost house-wide scope remains')

    direct_results = {}
    for buff_type in sorted(forbidden_house_types | {'production'}):
        reward = representatives.get(buff_type)
        if not reward:
            errors.append(f'no individual {buff_type} reward to audit')
            continue
        unit_id = str(reward['unit']).upper()
        counts = _active_direct_buff_counts(
            [reward],
            require_unlocked_access=False,
        )
        affected_ids = set(counts)
        allowed_ids = set(linked_buff_variant_ids(unit_id))
        if unit_id not in counts or not affected_ids.issubset(allowed_ids):
            errors.append(
                f'{buff_type} escaped exact unit identity: {sorted(affected_ids)}'
            )
        if stacked_house_buff_values(
            [reward], require_unlocked_access=False
        ):
            errors.append(f'individual {buff_type} still writes CountryType')
        direct_results[buff_type] = sorted(affected_ids)

    global_results = {}
    if global_production_reward:
        global_results = _active_direct_buff_counts(
            [global_production_reward],
            require_unlocked_access=False,
            global_production_unit_ids={'E1', 'HTNK'},
        )
        if set(global_results) != {'E1', 'HTNK'} or any(
            counts != {'production': 1}
            for counts in global_results.values()
        ):
            errors.append(
                f'All Production did not reach all audited units: {global_results}'
            )

    if errors:
        raise ValueError('House-wide buff policy failed: ' + '; '.join(errors))
    return {
        'house_wide_scopes': [list(scope) for scope in sorted(scope_set)],
        'individual_direct_results': direct_results,
        'all_production_direct_results': global_results,
    }
