"""Reading a stored skirmish run back, strictly but not brittly.

Two things are deliberately tolerated, because refusing them would put a
playable save on the corruption path: a map the installation no longer has,
and a country index the installed rules no longer describe. Both are checked
where they are used -- an offer whose map is gone cannot be launched -- and
neither is a reason to lose a run.
"""

from copy import deepcopy

from randomizer.core.integrity import strip_signature
from randomizer.shop.model import RunStatus

from .model import (
    SKIRMISH_RUN_COLLECTION_SCHEMA_VERSION,
    SKIRMISH_RUN_SCHEMA_VERSION,
    BattleOffer,
    UpgradePurchase,
    SkirmishRun,
    SkirmishRunCollection,
)


class SkirmishStateError(ValueError):
    """Raised when stored skirmish state cannot be read safely."""


def _object(value, field):
    if not isinstance(value, dict):
        raise SkirmishStateError(f'Skirmish field {field!r} must be an object')
    return value


def _string(value, field, *, required=False):
    if value is None and not required:
        return ''
    if not isinstance(value, str) or (required and not value):
        raise SkirmishStateError(
            f'Skirmish field {field!r} must be a '
            + ('non-empty string' if required else 'string')
        )
    return value


def _int(value, field, *, minimum=0, default=0):
    if value is None:
        value = default
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise SkirmishStateError(
            f'Skirmish field {field!r} must be an integer of at least {minimum}'
        )
    return value


def _version(document, current, label):
    version = document.get('schema_version', current)
    if not isinstance(version, int) or isinstance(version, bool):
        raise SkirmishStateError(f'{label} schema_version must be an integer')
    if version != current:
        raise SkirmishStateError(
            f'Unsupported {label} schema_version {version!r}; expected {current}'
        )
    return version


def normalize_battle_offer(document, field='offer'):
    document = _object(document, field)
    countries = document.get('enemy_countries')
    if not isinstance(countries, list) or not countries:
        raise SkirmishStateError(
            f'Skirmish field {field}.enemy_countries must be a non-empty list'
        )
    return BattleOffer(
        map_path=_string(
            document.get('map_path'), f'{field}.map_path', required=True
        ),
        map_name=_string(document.get('map_name'), f'{field}.map_name'),
        enemy_countries=tuple(
            _int(country, f'{field}.enemy_countries[]') for country in countries
        ),
        handicap=_int(document.get('handicap'), f'{field}.handicap'),
        # One per enemy. A run stored before a tier mixed them has none,
        # and every enemy takes the offer's own difficulty.
        handicaps=tuple(
            _int(value, f'{field}.handicaps[]')
            for value in (document.get('handicaps') or [])
            if isinstance(document.get('handicaps'), list)
        ),
        mental_ai=bool(document.get('mental_ai')),
        seed=_int(document.get('seed'), f'{field}.seed'),
        ally=bool(document.get('ally', True)),
        challenge=bool(document.get('challenge')),
    )


def normalize_purchases(value, field):
    """Read a purchase list, adding up any repeats of the same upgrade."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SkirmishStateError(f'Skirmish field {field!r} must be a list')
    combined = {}
    for index, raw in enumerate(value):
        record = _object(raw, f'{field}[{index}]')
        unit = _string(
            record.get('unit'), f'{field}[{index}].unit', required=True
        ).upper()
        buff_type = _string(
            record.get('buff_type'),
            f'{field}[{index}].buff_type',
            required=True,
        )
        stacks = _int(
            record.get('stacks'), f'{field}[{index}].stacks',
            minimum=1, default=1,
        )
        key = (unit, buff_type)
        combined[key] = combined.get(key, 0) + stacks
    return tuple(
        UpgradePurchase(unit, buff_type, stacks)
        for (unit, buff_type), stacks in combined.items()
    )


def _shelf(value):
    """Return the shop offers a stored run was in the middle of."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        str(item) for item in value
        if isinstance(item, str) and ':' in item
    )


def normalize_skirmish_run(document):
    document = deepcopy(_object(strip_signature(document), 'run'))
    _version(document, SKIRMISH_RUN_SCHEMA_VERSION, 'Skirmish run')
    try:
        status = RunStatus(document.get('status', RunStatus.ACTIVE.value))
    except ValueError as exc:
        raise SkirmishStateError(
            f'Invalid Skirmish run status {document.get("status")!r}'
        ) from exc
    offers = document.get('offers') or []
    if not isinstance(offers, list):
        raise SkirmishStateError('Skirmish field offers must be a list')
    parsed_offers = tuple(
        normalize_battle_offer(offer, f'offers[{index}]')
        for index, offer in enumerate(offers)
    )
    committed = document.get('committed_offer')
    if committed is not None:
        committed = _int(committed, 'committed_offer')
        if committed >= len(parsed_offers):
            raise SkirmishStateError(
                f'Skirmish committed_offer {committed} names no offer'
            )
    used = document.get('used_challenge_maps') or []
    if not isinstance(used, list):
        raise SkirmishStateError(
            'Skirmish field used_challenge_maps must be a list'
        )
    return SkirmishRun(
        run_id=_string(document.get('run_id'), 'run_id', required=True),
        seed=_string(document.get('seed'), 'seed', required=True),
        created=_string(document.get('created'), 'created'),
        status=status,
        player_country=_int(document.get('player_country'), 'player_country'),
        ally_country=_int(document.get('ally_country'), 'ally_country'),
        battle=_int(document.get('battle'), 'battle', minimum=1, default=1),
        lives=_int(document.get('lives'), 'lives', minimum=1, default=1),
        revivals_used=_int(document.get('revivals_used'), 'revivals_used'),
        coins=_int(document.get('coins'), 'coins'),
        purchases=normalize_purchases(document.get('purchases'), 'purchases'),
        ally_coins=_int(document.get('ally_coins'), 'ally_coins'),
        ally_purchases=normalize_purchases(
            document.get('ally_purchases'), 'ally_purchases'
        ),
        offers=parsed_offers,
        shelf=_shelf(document.get('shelf')),
        committed_offer=committed,
        won_battles=_int(document.get('won_battles'), 'won_battles'),
        used_challenge_maps=tuple(
            dict.fromkeys(
                _string(path, 'used_challenge_maps[]', required=True)
                for path in used
            )
        ),
    )


def normalize_skirmish_run_collection(document):
    if document is None:
        return SkirmishRunCollection()
    document = deepcopy(_object(strip_signature(document), 'runs'))
    _version(
        document,
        SKIRMISH_RUN_COLLECTION_SCHEMA_VERSION,
        'Skirmish run list',
    )
    raw_runs = document.get('runs')
    if not isinstance(raw_runs, list):
        raise SkirmishStateError("Skirmish field 'runs' must be a list")
    runs = []
    seen = set()
    for index, raw_run in enumerate(raw_runs):
        run = normalize_skirmish_run(_object(raw_run, f'runs[{index}]'))
        if run.run_id in seen:
            raise SkirmishStateError(f'Duplicate Skirmish run_id {run.run_id!r}')
        seen.add(run.run_id)
        runs.append(run)
    active = document.get('active_run_id')
    if active is not None and not isinstance(active, str):
        raise SkirmishStateError('Skirmish active_run_id must be a string')
    return SkirmishRunCollection(
        runs=tuple(runs),
        # An id naming no stored run reads as no active run: the runs are
        # intact and "between runs" is a state the mode already opens in.
        active_run_id=active if active in seen else None,
    )
