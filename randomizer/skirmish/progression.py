"""How a run gets harder, and what it offers next.

Battles are grouped into tiers, and the battle that closes a tier is a
challenge -- fought on a challenge map, with no choice of which. The early
tiers are short: two battles and a challenge, then three, then four for the
rest of the run, because five fights against one enemy is four repeats of
the same fight. Everything a tier decides is in one table, so what the mode
does at battle twelve can be read rather than traced.

What rises with the tier is the number of enemies, how well they play, how
often the ally is missing, and how much of an army each enemy has bought
for itself. The last of those is new: an enemy used to field the units the
rules give it and nothing more, while the player and the ally both spent a
run getting better, so the fight got easier as the numbers got bigger.

An enemy plays a different country nearly every battle, so it cannot shop
the way the ally does -- there is nothing for it to keep. Instead each one
is handed a set of upgrades for the country it is playing, drawn fresh from
that country's own shelf when the battle is offered, which over a run is a
draw across every faction's pool.

Offers are drawn from the run's seed and its battle number, so the same run
opened twice offers the same battles, and the offer that was stored is the
one that is played.
"""

from dataclasses import dataclass
import random

from .challenges import challenge_for
from .model import (
    WARMUP_BATTLE,
    BattleOffer,
    closes_tier,
    tier_of,
)
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

    ``enemy_upgrades`` is how many upgrades each enemy is handed for the
    country it is playing. The first tier hands out none: the opening
    fight is against the army the rules describe, and an offer has to ask
    for a bought-up enemy before one appears.
    """

    enemies: tuple[int, ...]
    challenge: int
    mental: bool = False
    challenge_mental: bool = False
    enemy_upgrades: int = 0

    @property
    def handicap(self):
        """The tier's headline difficulty: the best of its enemies."""
        return min(self.enemies) if self.enemies else AI_DIFFICULTY_MEDIUM


# Nine tiers, and the first is already a fair fight. An easy AI does not
# make an easy battle, it makes a quiet one: it barely attacks, and Mental
# Omega's own boost makes that worse rather than better, because on Easy it
# raises the team delay from 90 to 1000. So nothing here is fought on Easy.
TIERS = (
    Tier(
        enemies=(AI_DIFFICULTY_MEDIUM,),
        challenge=AI_DIFFICULTY_EASY,
        enemy_upgrades=0,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_MEDIUM),
        challenge=AI_DIFFICULTY_EASY,
        enemy_upgrades=1,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD),
        challenge=AI_DIFFICULTY_MEDIUM,
        enemy_upgrades=1,
    ),
    Tier(
        enemies=(
            AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD,
        ),
        challenge=AI_DIFFICULTY_MEDIUM,
        enemy_upgrades=2,
    ),
    Tier(
        enemies=(
            AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD, AI_DIFFICULTY_HARD,
        ),
        challenge=AI_DIFFICULTY_HARD,
        enemy_upgrades=2,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_HARD,) * 3,
        challenge=AI_DIFFICULTY_HARD,
        enemy_upgrades=3,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_HARD,) * 3,
        challenge=AI_DIFFICULTY_HARD,
        mental=True,
        challenge_mental=True,
        enemy_upgrades=4,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_HARD,) * 4,
        challenge=AI_DIFFICULTY_HARD,
        mental=True,
        challenge_mental=True,
        enemy_upgrades=4,
    ),
    Tier(
        enemies=(AI_DIFFICULTY_HARD,) * 5,
        challenge=AI_DIFFICULTY_HARD,
        mental=True,
        enemy_upgrades=5,
    ),
)
# The warmup. One trained enemy and the ally beside you, no shop, no
# challenge and no life at stake: a fight to find the mouse again before
# the run starts counting. It can be skipped.
WARMUP = Tier(enemies=(AI_DIFFICULTY_MEDIUM,), challenge=AI_DIFFICULTY_EASY)
OFFER_COUNT = 5


@dataclass(frozen=True)
class Modifier:
    """One thing an offer may ask for, and what it pays for asking.

    Battles that differ only in which map they are on are not a choice,
    they are a shuffle -- which is what three offers made of three fixed
    bonuses were. So an offer is now composed: the plain battle, and then
    combinations drawn from this table, at most two at once.

    ``from_tier`` is where a modifier becomes askable. Nothing is asked of
    a run before the run can answer it.
    """

    key: str
    label: str
    percent: int
    from_tier: int = 1
    extra_enemies: int = 0
    alone: bool = False
    mental: bool = False
    # How many upgrades this adds to what each enemy already carries.
    enemy_upgrades: int = 0


# What each one is worth is what it costs to survive, not what it sounds
# like. Fighting without the ally used to pay 75% and was the easiest of
# the three offers on a one-enemy tier: an ally is one more base to defend
# and one more army walking into things. One more enemy is the harder ask
# and now pays the more, and a bought-up enemy sits between them.
MODIFIERS = (
    Modifier('alone', 'no ally', 25, alone=True),
    Modifier('armed', 'a bought-up enemy', 35, enemy_upgrades=2),
    Modifier('extra_enemy', 'one more enemy', 40, extra_enemies=1),
    Modifier('boost', 'boosted AI', 50, from_tier=4, mental=True),
)
MODIFIERS_BY_KEY = {one.key: one for one in MODIFIERS}
# How many may be asked for at once. Three at a time is not an offer, it
# is a punishment, and the percentages add up faster than a run does.
MAX_STACKED = 2
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
    return tier_of(battle)


def tier_rules(battle):
    """The tier's own table, with the last tier standing for every one after."""
    if is_warmup(battle):
        return WARMUP
    return TIERS[min(tier_for(battle), len(TIERS)) - 1]


def is_challenge_battle(battle):
    """Whether this battle closes a tier. The warmup closes nothing."""
    return closes_tier(battle)


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


def allowed_modifiers(battle):
    """Return what this battle is allowed to ask for."""
    if is_warmup(battle):
        return ()
    tier = tier_for(battle)
    return tuple(one for one in MODIFIERS if tier >= one.from_tier)


def _asks(allowed):
    """Return every combination that may be asked for, easiest first.

    The plain battle leads, and then every set of one or two, ordered by
    what they add up to -- so an offer list reads from the fight a run can
    take to the fight it is gambling on.
    """
    from itertools import combinations

    sets = [()]
    for size in range(1, MAX_STACKED + 1):
        sets.extend(combinations(allowed, size))
    sets[1:] = sorted(
        sets[1:],
        key=lambda ask: (sum(one.percent for one in ask), [
            one.key for one in ask
        ]),
    )
    return sets


def offer_modifiers(battle, count=OFFER_COUNT, seed=''):
    """Return what each of this battle's offers asks for, in order.

    The plain offer is always first and always present -- a run that has
    nothing left should be able to take a battle that asks nothing of it.
    The rest are drawn, so two runs at the same tier are not handed the
    same list, and no two offers in one list ask for the same things.

    The warmup asks for nothing: it is the fight before the run starts
    counting, and a bonus on it would be a reward for not being warmed up.
    """
    count = max(1, int(count))
    allowed = allowed_modifiers(battle)
    if not allowed:
        return tuple(() for _ in range(count))
    asks = _asks(allowed)
    generator = _rng(seed, battle, 'modifiers')
    taken = generator.sample(asks[1:], min(count - 1, len(asks) - 1))
    taken.sort(key=lambda ask: sum(one.percent for one in ask))
    drawn = [()] + taken
    while len(drawn) < count:
        drawn.append(())
    return tuple(drawn)


def _enemy_upgrades(country, many, generator):
    """Return the upgrades one enemy is handed, as ``unit:buff_type`` keys.

    Drawn from the shelf its own country shops from, because an upgrade
    for a unit this army cannot field is Ore spent on nothing -- and since
    an enemy plays a different country nearly every battle, a run's
    enemies are bought up out of every faction's list in turn.
    """
    if many <= 0 or not country:
        return ()
    from .ownership import STOLEN_TECH_GROUP
    from .shop import country_upgrades

    # Not the stolen-tech row. What puts those units on the field is an
    # infiltration, which is not something a computer player is handed
    # with its upgrades -- buying one for an enemy would improve a unit
    # that never arrives.
    shelf = [
        one for one in country_upgrades(country)
        if one.unit != STOLEN_TECH_GROUP
    ]
    if not shelf:
        return ()
    return tuple(sorted(
        f'{one.unit}:{one.buff_type}'
        for one in generator.sample(shelf, min(many, len(shelf)))
    ))


def battle_offers(run, pool, maps_dir, countries, *, count=OFFER_COUNT):
    """Return the battles offered for this run's current battle number."""
    if not pool or not countries:
        return ()
    rules = tier_rules(run.battle)
    generator = _rng(run.seed, run.battle)
    ordered = sorted(pool, key=lambda entry: entry.path.name)
    offers = []
    chosen = set()
    asked = offer_modifiers(run.battle, count, seed=run.seed)
    for index in range(count):
        ask = asked[index]
        # The body an offer adds is one of the tier's own, not its worst:
        # a fourth enemy at the difficulty the tier already fields is one
        # more army, which is what the offer says it is.
        extra = sum(one.extra_enemies for one in ask)
        handicaps = rules.enemies + tuple(
            rules.enemies[0] for _ in range(extra)
        )
        ally = not any(one.alone for one in ask)
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
        many = rules.enemy_upgrades + sum(one.enemy_upgrades for one in ask)
        # An armed enemy may not play the ally's country. A copy is gated
        # to a country rather than to a house, so arming that enemy would
        # arm the ally with it -- and the launch, which cannot do that,
        # would send it plain against an offer that promised otherwise and
        # was paid for.
        drawn_from = countries
        if many > 0 and ally:
            spare = [
                country for country in countries
                if country.index != run.ally_country
            ]
            drawn_from = spare or countries
        enemy_countries = tuple(
            generator.choice(drawn_from).index for _ in range(enemies)
        )
        offers.append(BattleOffer(
            map_path=_relative(entry.path, maps_dir),
            map_name=entry.name,
            enemy_countries=enemy_countries,
            handicap=rules.handicap,
            handicaps=handicaps,
            mental_ai=rules.mental or any(one.mental for one in ask),
            bonus_percent=sum(one.percent for one in ask),
            modifiers=tuple(one.key for one in ask),
            enemy_upgrades=tuple(
                _enemy_upgrades(
                    _country_id(countries, index), many, generator,
                )
                for index in enemy_countries
            ),
            seed=generator.randrange(1, 2 ** 31),
            ally=ally,
            challenge=False,
        ))
    return tuple(offers)


def _country_id(countries, index):
    """Return the rules name of a country, when the caller has one."""
    for country in countries:
        if country.index == index:
            return str(getattr(country, 'country_id', '') or '')
    return ''


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
    # What each enemy brought that the rules did not give it. Said as a
    # count rather than a list: the units are the enemy's business, and
    # what a player needs to know before choosing is how many.
    carried = max(
        (len(bought) for bought in offer.enemy_upgrades), default=0,
    )
    armed = (
        f', {"each " if enemies > 1 else ""}carrying {carried} '
        f'{"upgrade" if carried == 1 else "upgrades"}'
        if carried else ''
    )
    reward = (
        f'\n+{offer.bonus_percent}% Ore for taking it'
        if offer.bonus_percent else ''
    )
    return (
        f'{" and ".join(parts)} {"enemy" if enemies == 1 else "enemies"}'
        f'{boost}{armed}, {company}{reward}'
    )
