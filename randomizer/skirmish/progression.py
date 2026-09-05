"""How a run gets harder, and what it offers next.

The shape follows Shop Mode: battles are grouped into tiers of five, and the
battle that closes a tier is a challenge -- fought on a challenge map, with
no choice of which. Everything a tier decides is in one table, so what the
mode does at battle twelve can be read rather than traced.

What rises with the tier is the number of enemies, how well they play, and
how often the ally is missing. What does not rise here is the enemy's own
strength: the rules injection that buffs an opposition is the Shop mode's
machinery, and until a skirmish launch generates rules it is not available.

Offers are drawn from the run's seed and its battle number, so the same run
opened twice offers the same battles, and the offer that was stored is the
one that is played.
"""

from dataclasses import dataclass
import random

from .model import BATTLES_PER_TIER, BattleOffer
from .spawn import (
    AI_HANDICAP_HARD,
    AI_HANDICAP_NORMAL,
)


@dataclass(frozen=True)
class Tier:
    enemies: tuple[int, ...]
    handicap: int
    # Out of every ``ally_absent_in`` offers, one is fought without the ally.
    # Zero means the ally is always there.
    ally_absent_in: int = 0


TIERS = (
    Tier(enemies=(1, 1, 2), handicap=AI_HANDICAP_NORMAL),
    Tier(enemies=(2,), handicap=AI_HANDICAP_HARD, ally_absent_in=3),
    Tier(enemies=(2, 3), handicap=AI_HANDICAP_HARD, ally_absent_in=3),
    Tier(enemies=(3,), handicap=AI_HANDICAP_HARD, ally_absent_in=2),
)
OFFER_COUNT = 3


def tier_for(battle):
    """Which tier a battle belongs to, counted from one."""
    return (max(1, int(battle)) - 1) // BATTLES_PER_TIER + 1


def tier_rules(battle):
    """The tier's own table, with the last tier standing for every one after."""
    return TIERS[min(tier_for(battle), len(TIERS)) - 1]


def is_challenge_battle(battle):
    return max(1, int(battle)) % BATTLES_PER_TIER == 0


def _rng(seed, battle, salt=''):
    return random.Random(f'{seed}:{battle}:{salt}')


def _relative(path, maps_dir):
    try:
        return path.relative_to(maps_dir).as_posix()
    except ValueError:
        return path.name


def challenge_offer(run, pool, maps_dir, countries):
    """Return the one challenge that closes this tier.

    A challenge map is not offered again until the pool has been through
    once; when the last one is used the pool comes back whole.
    """
    if not pool:
        return None
    used = set(run.used_challenge_maps)
    remaining = [
        entry for entry in pool
        if _relative(entry.path, maps_dir) not in used
    ]
    if not remaining:
        remaining = list(pool)
    rules = tier_rules(run.battle)
    generator = _rng(run.seed, run.battle, 'challenge')
    entry = generator.choice(sorted(remaining, key=lambda item: item.name))
    # A challenge seats what it seats. The opposition fills the map rather
    # than the tier deciding, since the fight is the map's own.
    enemies = max(1, min(entry.seats - 2, max(rules.enemies)))
    return BattleOffer(
        map_path=_relative(entry.path, maps_dir),
        map_name=entry.name,
        enemy_countries=tuple(
            generator.choice(countries).index for _ in range(enemies)
        ),
        handicap=rules.handicap,
        seed=generator.randrange(1, 2 ** 31),
        ally=entry.seats > enemies + 1,
        challenge=True,
    )


def battle_offers(run, pool, maps_dir, countries, *, count=OFFER_COUNT):
    """Return the battles offered for this run's current battle number."""
    if not pool or not countries:
        return ()
    rules = tier_rules(run.battle)
    generator = _rng(run.seed, run.battle)
    ordered = sorted(pool, key=lambda entry: entry.path.name)
    offers = []
    chosen = set()
    for index in range(count):
        enemies = rules.enemies[index % len(rules.enemies)]
        ally = not (
            rules.ally_absent_in
            and index % rules.ally_absent_in == rules.ally_absent_in - 1
        )
        seats = 1 + enemies + (1 if ally else 0)
        candidates = [
            entry for entry in ordered
            if entry.seats >= seats
            and entry.minimum_players <= seats
            and str(entry.path) not in chosen
        ]
        if not candidates:
            continue
        entry = generator.choice(candidates)
        chosen.add(str(entry.path))
        offers.append(BattleOffer(
            map_path=_relative(entry.path, maps_dir),
            map_name=entry.name,
            enemy_countries=tuple(
                generator.choice(countries).index for _ in range(enemies)
            ),
            handicap=rules.handicap,
            seed=generator.randrange(1, 2 ** 31),
            ally=ally,
            challenge=False,
        ))
    return tuple(offers)


def offers_for(run, standard_pool, challenge_pool, maps_dir, countries):
    """Return what this battle offers: three to choose from, or one challenge."""
    if is_challenge_battle(run.battle):
        offer = challenge_offer(run, challenge_pool, maps_dir, countries)
        return (offer,) if offer is not None else ()
    return battle_offers(run, standard_pool, maps_dir, countries)


def describe_offer(offer):
    """One line saying what taking this battle means."""
    enemies = len(offer.enemy_countries)
    company = 'with your ally' if offer.ally else 'alone'
    skill = {
        AI_HANDICAP_NORMAL: 'trained',
        AI_HANDICAP_HARD: 'hardened',
    }.get(offer.handicap, 'green')
    return (
        f'{enemies} {skill} '
        f'{"enemy" if enemies == 1 else "enemies"}, {company}'
    )
