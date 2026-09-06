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

from .challenges import challenge_for
from .model import BATTLES_PER_TIER, WARMUP_BATTLE, BattleOffer
from .spawn import (
    AI_DIFFICULTY_EASY,
    AI_DIFFICULTY_HARD,
    AI_DIFFICULTY_MEDIUM,
)


@dataclass(frozen=True)
class Tier:
    """What one tier's battles are made of.

    ``enemies`` is the difficulty of each enemy in the tier's own battle,
    so its length is how many there are and its contents are how well they
    play. ``challenge`` is which of the client's three challenge modes
    closes the tier, and the two ``mental`` flags say whether Mental
    Omega's AI boost is on for the tier's battles and for its challenge.
    """

    enemies: tuple[int, ...]
    challenge: int
    mental: bool = False
    challenge_mental: bool = False

    @property
    def handicap(self):
        """The tier's headline difficulty: the best of its enemies."""
        return min(self.enemies) if self.enemies else AI_DIFFICULTY_MEDIUM


# Nine tiers, and the first is already a fair fight. An easy AI does not
# make an easy battle, it makes a quiet one: it barely attacks, and Mental
# Omega's own boost makes that worse rather than better, because on Easy it
# raises the team delay from 90 to 1000. So nothing here is fought on Easy.
TIERS = (
    Tier(enemies=(AI_DIFFICULTY_MEDIUM,), challenge=AI_DIFFICULTY_EASY),
    Tier(
        enemies=(AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_MEDIUM),
        challenge=AI_DIFFICULTY_EASY,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD),
        challenge=AI_DIFFICULTY_MEDIUM,
    ),
    Tier(
        enemies=(
            AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD,
        ),
        challenge=AI_DIFFICULTY_MEDIUM,
    ),
    Tier(
        enemies=(
            AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD, AI_DIFFICULTY_HARD,
        ),
        challenge=AI_DIFFICULTY_HARD,
    ),
    Tier(enemies=(AI_DIFFICULTY_HARD,) * 3, challenge=AI_DIFFICULTY_HARD),
    Tier(
        enemies=(AI_DIFFICULTY_HARD,) * 3,
        challenge=AI_DIFFICULTY_HARD,
        mental=True,
        challenge_mental=True,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_HARD,) * 4,
        challenge=AI_DIFFICULTY_HARD,
        mental=True,
        challenge_mental=True,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_HARD,) * 5,
        challenge=AI_DIFFICULTY_HARD,
        mental=True,
    ),
)
# The warmup. One trained enemy and the ally beside you, no shop, no
# challenge and no life at stake: a fight to find the mouse again before
# the run starts counting. It can be skipped.
WARMUP = Tier(enemies=(AI_DIFFICULTY_MEDIUM,), challenge=AI_DIFFICULTY_EASY)
OFFER_COUNT = 3


@dataclass(frozen=True)
class Bonus:
    """What one of the harder offers asks, and what it pays for asking.

    Three battles that differ only in which map they are on is not a
    choice, it is a shuffle. So two of the three cost something -- one more
    enemy, the ally left at home, an AI playing with Mental Omega's own
    boost -- and pay a percentage on top for it.
    """

    label: str
    percent: int
    extra_enemies: int = 0
    alone: bool = False
    mental: bool = False


# The plain offer first, then the two that ask for something. A run that
# wants Ore takes the third; a run that wants to survive takes the first.
BONUSES = (
    Bonus(label='', percent=0),
    Bonus(label='one more enemy', percent=40, extra_enemies=1),
    Bonus(label='no ally', percent=75, alone=True),
)
# From the tier that fields three enemies onwards, the dearest offer asks
# for the boosted AI instead of a fourth body on the field.
BOOSTED_BONUS = Bonus(label='boosted AI, no ally', percent=110, alone=True, mental=True)
BOOSTED_FROM_TIER = 4
# What the ally plays at, whatever the enemies play at. It is the player's
# partner, and a partner on Easy develops a base and then stands in it: the
# difficulty of a run is what it is fought against, not who it is fought
# beside.
ALLY_DIFFICULTY = AI_DIFFICULTY_HARD


def is_warmup(battle):
    """Whether this is the fight before the run starts counting."""
    return int(battle) <= WARMUP_BATTLE


def tier_for(battle):
    """Which tier a battle belongs to. The warmup is tier zero."""
    battle = int(battle)
    if is_warmup(battle):
        return WARMUP_BATTLE
    return (battle - 1) // BATTLES_PER_TIER + 1


def tier_rules(battle):
    """The tier's own table, with the last tier standing for every one after."""
    if is_warmup(battle):
        return WARMUP
    return TIERS[min(tier_for(battle), len(TIERS)) - 1]


def is_challenge_battle(battle):
    """Whether this battle closes a tier. The warmup closes nothing."""
    if is_warmup(battle):
        return False
    return int(battle) % BATTLES_PER_TIER == 0


def _rng(seed, battle, salt=''):
    return random.Random(f'{seed}:{battle}:{salt}')


def _relative(path, maps_dir):
    try:
        return path.relative_to(maps_dir).as_posix()
    except ValueError:
        return path.name


def challenge_level(battle):
    """Which of the client's three challenge modes closes this tier."""
    return tier_rules(battle).challenge


def challenge_offer(run, pool, maps_dir, countries):
    """Return the one challenge that closes this tier.

    A challenge is the map's own fight: the client describes each one with
    the three armies it was designed against, and those are the armies it is
    played against here. What the tier decides is only which of the client's
    three challenge modes it is fought under.

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
    generator = _rng(run.seed, run.battle, 'challenge')
    entry = generator.choice(sorted(remaining, key=lambda item: item.name))
    relative = _relative(entry.path, maps_dir)
    described = challenge_for(relative)
    if described is not None and described.houses:
        enemies = tuple(house.country for house in described.houses)
    else:
        # A map the installation lists nowhere: the opposition fills what
        # the map seats, so the fight is at least the right size.
        rules = tier_rules(run.battle)
        enemies = tuple(
            generator.choice(countries).index
            for _ in range(max(1, min(entry.seats - 1, len(rules.enemies))))
        )
    return BattleOffer(
        map_path=relative,
        map_name=entry.name,
        enemy_countries=enemies,
        handicap=challenge_level(run.battle),
        handicaps=tuple(
            challenge_level(run.battle) for _ in enemies
        ),
        mental_ai=tier_rules(run.battle).challenge_mental,
        seed=generator.randrange(1, 2 ** 31),
        # A challenge is fought alone. The second start on those maps is the
        # co-op partner's, and the fight was balanced for who stands in it.
        ally=False,
        challenge=True,
    )


def offer_bonuses(battle, count=OFFER_COUNT):
    """Return what each of this battle's offers asks for, in order.

    The warmup asks for nothing: it is the fight before the run starts
    counting, and a bonus on it would be a reward for not being warmed up.
    """
    if is_warmup(battle):
        return tuple(BONUSES[0] for _ in range(count))
    table = list(BONUSES[:count])
    if tier_for(battle) >= BOOSTED_FROM_TIER and len(table) > 2:
        # Three enemies is already a crowd. What the dearest offer asks for
        # from here on is a better opponent rather than another one.
        table[-1] = BOOSTED_BONUS
    while len(table) < count:
        table.append(BONUSES[0])
    return tuple(table)


def battle_offers(run, pool, maps_dir, countries, *, count=OFFER_COUNT):
    """Return the battles offered for this run's current battle number."""
    if not pool or not countries:
        return ()
    rules = tier_rules(run.battle)
    generator = _rng(run.seed, run.battle)
    ordered = sorted(pool, key=lambda entry: entry.path.name)
    offers = []
    chosen = set()
    bonuses = offer_bonuses(run.battle, count)
    for index in range(count):
        bonus = bonuses[index]
        handicaps = rules.enemies + tuple(
            rules.enemies[-1] for _ in range(bonus.extra_enemies)
        )
        ally = not bonus.alone
        enemies = len(handicaps)
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
            handicaps=handicaps,
            mental_ai=rules.mental or bonus.mental,
            bonus_percent=bonus.percent,
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


SKILL_NAMES = {
    AI_DIFFICULTY_EASY: 'green',
    AI_DIFFICULTY_MEDIUM: 'trained',
    AI_DIFFICULTY_HARD: 'hardened',
}


def describe_offer(offer):
    """One line saying what taking this battle means."""
    counted = {}
    for handicap in offer.enemy_handicaps():
        skill = SKILL_NAMES.get(handicap, 'trained')
        counted[skill] = counted.get(skill, 0) + 1
    parts = [
        f'{count} {skill}' for skill, count in sorted(
            counted.items(), key=lambda item: -item[1]
        )
    ]
    enemies = len(offer.enemy_countries)
    company = 'with your ally' if offer.ally else 'alone'
    boost = ', boosted AI' if offer.mental_ai else ''
    reward = (
        f'\n+{offer.bonus_percent}% Ore for taking it'
        if offer.bonus_percent else ''
    )
    return (
        f'{" and ".join(parts)} {"enemy" if enemies == 1 else "enemies"}'
        f'{boost}, {company}{reward}'
    )
