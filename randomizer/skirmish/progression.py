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

from .challenges import challenge_for, in_first_walk
from .config import SETTINGS, difficulty_number
from .shop import earned_by
from .model import (
    WARMUP_BATTLE,
    BattleOffer,
    UpgradePurchase,
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


# The ladder, read from ``configs/skirmish.json``. Nothing here is fought
# on Easy: an easy AI does not make an easy battle, it makes a quiet one --
# it barely attacks, and Mental Omega's own boost makes that worse rather
# than better, because on Easy it raises the team delay from 90 to 1000.
# That is a thing to know while tuning the file, not a thing this enforces.
TIERS = tuple(
    Tier(
        enemies=one.enemies,
        challenge=one.challenge,
        mental=one.mental,
        challenge_mental=one.challenge_mental,
        enemy_upgrades=one.enemy_upgrades,
    )
    for one in SETTINGS.tiers
)
# The warmup. One enemy and the ally beside you, no shop, no challenge and
# no life at stake: a fight to find the mouse again before the run starts
# counting. It can be skipped.
WARMUP = Tier(
    enemies=SETTINGS.warmup.enemies,
    challenge=SETTINGS.warmup.challenge,
    mental=SETTINGS.warmup.mental,
    challenge_mental=SETTINGS.warmup.challenge_mental,
    enemy_upgrades=SETTINGS.warmup.enemy_upgrades,
)
# How many battles a table sets. Battles that differ only in which map
# they are on are a shuffle rather than a choice, so the table is the
# plain battle and then combinations of what a tier allows.
OFFER_COUNT = int(SETTINGS.shelf['offer_count'])


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
    # How many stats each enemy's whole army is bought up in for this
    # battle. A tier hands out units; an offer that asks for a bought-up
    # enemy is asking for something else entirely -- an army that is
    # better everywhere, on that map, for that fight.
    faction_upgrades: int = 0
    # Whether each enemy fields the units its country can only field by
    # infiltrating somebody. The AI has always had teams that name them --
    # all fifteen appear in Mental Omega's own task forces -- and has
    # never been able to build one, because it cannot infiltrate.
    enemy_stolen: bool = False


# What each one is worth is what it costs to survive, not what it sounds
# like -- which is a judgement, and lives in the file with the numbers.
MODIFIERS = tuple(
    Modifier(
        key=one.key,
        label=one.label,
        percent=one.percent,
        from_tier=one.from_tier,
        extra_enemies=one.extra_enemies,
        alone=one.alone,
        mental=one.mental,
        enemy_upgrades=one.enemy_upgrades,
        faction_upgrades=one.faction_upgrades,
        enemy_stolen=one.enemy_stolen,
    )
    for one in SETTINGS.modifiers
)
MODIFIERS_BY_KEY = {one.key: one for one in MODIFIERS}
# How many may be asked for at once. Three at a time is not an offer, it
# is a punishment, and the percentages add up faster than a run does.
MAX_STACKED = int(SETTINGS.shelf['max_stacked_modifiers'])
# What the ally plays at, whatever the enemies play at. It is the player's
# partner, and a partner on Easy develops a base and then stands in it: the
# difficulty of a run is what it is fought against, not who it is fought
# beside.
ALLY_DIFFICULTY = difficulty_number(SETTINGS.enemy['ally_difficulty'])


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


def _walkable(run, pool, maps_dir):
    """Return the challenges this run has earned the right to be dealt.

    The client's later challenges are a different game from its early ones,
    so a first walk closes its tiers on the first twelve and the rest wait
    for nightmare. An installation that numbers none of them keeps all of
    them: the holding back is the client's own ordering, not a guess.
    """
    if run.nightmare:
        return list(pool)
    walkable = [
        entry for entry in pool
        if in_first_walk(challenge_for(_relative(entry.path, maps_dir)))
    ]
    return walkable or list(pool)


def challenge_offer(run, pool, maps_dir, countries):
    """Return the one challenge that closes this tier.

    A challenge is the map's own fight: the client describes each one with
    the three armies it was designed against, and those are the armies it is
    played against here. What the tier decides is only which of the client's
    three challenge modes it is fought under.

    A challenge map is not offered again until the pool has been through
    once; when the last one is used the pool comes back whole -- the pool
    this run may walk, so a first walk never falls through to the late
    challenges by running out of early ones.
    """
    if not pool:
        return None
    pool = _walkable(run, pool, maps_dir)
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
        # The one thing a challenge gives back. It is the tier's own
        # fight, on a map built for it, and this is where a prototype
        # belongs: one unit of the player's country that the run could
        # otherwise only take by infiltrating somebody, theirs for this
        # battle and gone with it.
        player_stolen=_a_stolen_unit(
            _country_id(countries, run.player_country), generator,
        ),
        handicap=challenge_level(run.battle),
        handicaps=tuple(
            challenge_level(run.battle) for _ in enemies
        ),
        mental_ai=tier_rules(run.battle).challenge_mental,
        seed=generator.randrange(1, 2 ** 31),
        # The ally stands in the co-op partner's start, which every one of
        # these maps keeps free. The scripted armies are what they always
        # were; what changes is that the run does not meet them alone.
        ally=True,
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


def _a_stolen_unit(country, generator):
    """Return one unit this country could only field by infiltrating."""
    if not country:
        return ''
    from .ownership import stolen_tech_units

    found = sorted(stolen_tech_units(country))
    return generator.choice(found) if found else ''

def _enemy_upgrades(country, budget, generator):
    """Return what one enemy has spent its Ore on, as shelf keys.

    An enemy does not shop -- it plays a different country nearly every
    battle and has nothing to keep -- so what it carries is set for it,
    out of the same list that country would shop from, up to the Ore a
    run has had in hand by this battle.

    It pays what the player pays: the list price, and the same rise for
    everything already owned. So an army armed with 375 Ore has bought
    what 375 Ore buys, not what 375 Ore would buy at a discount.
    """
    if budget <= 0 or not country:
        return ()
    from .ownership import STOLEN_TECH_GROUP
    from .powers import superweapon_ids
    from .shop import country_upgrades, price_for

    # Not the stolen-tech row: what puts those units on the field is an
    # infiltration, and an offer that wants them there says so and hands
    # them over. And not a unit no task force names, because a computer
    # player builds what its task forces name -- an upgrade on anything
    # else is Ore spent on a unit that never arrives. A superweapon is
    # neither: the house builds the structure and the power comes with it.
    from .ai import fielded_by_ai

    fielded = fielded_by_ai()
    powers = superweapon_ids()
    shelf = [
        one for one in country_upgrades(country)
        if one.unit != STOLEN_TECH_GROUP
        # Nor anything that only lets it see further, which it does not
        # need to see with.
        and one.buff_type not in ENEMY_UNBOUGHT_BUFFS
        and (
            one.unit in powers
            or not fielded
            or one.unit in fielded
        )
    ]
    if not shelf:
        return ()
    generator.shuffle(shelf)
    bought = []
    spent = 0
    for one in shelf:
        price = price_for(one)
        if spent + price > budget:
            continue
        bought.append(UpgradePurchase(one.unit, one.buff_type, 1))
        spent += price
    return tuple(sorted(
        f'{one.unit}:{one.buff_type}' for one in bought
    ))


# What an enemy is never bought.
#
# A computer player is not playing against the fog: it knows where the
# player's army is whether or not its own units can see that far. Ore
# spent on seeing is Ore spent on nothing, and a battle that charged the
# offer for it would be charging for nothing too.
ENEMY_UNBOUGHT_BUFFS = frozenset(SETTINGS.enemy['unbought_buffs'])

# What an enemy army can be bought up in, and what to call one of those
# where a player reads it. Not every stat the shelf sells means anything
# across a whole army: an army that is entirely cloaked is not a harder
# battle, it is a battle the player cannot see; carrying stats belong to
# the few units that carry anything; and cost and production are what a
# shopper cares about, which a computer player is not.
FACTION_STAT_LABELS = dict(SETTINGS.enemy['faction_stats'])
FACTION_STATS = tuple(FACTION_STAT_LABELS)


def faction_stat_label(stat):
    """Return what an army-wide upgrade in one stat is called."""
    stat = str(stat or '')
    return FACTION_STAT_LABELS.get(stat) or stat.replace('_', ' ').title()

def _faction_upgrades(country, many, generator):
    """Return the stats one enemy's whole army is bought up in.

    Not what a tier hands out -- that is units, above. This is what the
    ``armed`` modifier buys when an offer asks for it: for that battle,
    on that map, the enemy army is better everywhere rather than in a few
    places, which is what makes the offer worth the percentage it pays.

    Drawn from the stats its own country's shelf sells, so an army is only
    ever bought up in something its units have.
    """
    if many <= 0 or not country:
        return ()
    from .ownership import STOLEN_TECH_GROUP
    from .shop import country_upgrades

    # Not the stolen-tech row: what puts those units on the field is an
    # infiltration, and an offer that wants them there says so and hands
    # them over. And not a unit no task force names, because a computer
    # player builds what its task forces name.
    from .ai import fielded_by_ai

    fielded = fielded_by_ai()
    sold = {
        one.buff_type for one in country_upgrades(country)
        if one.unit != STOLEN_TECH_GROUP
        and (not fielded or one.unit in fielded)
    }
    shelf = [stat for stat in FACTION_STATS if stat in sold]
    if not shelf:
        return ()
    return tuple(sorted(
        generator.sample(shelf, min(many, len(shelf)))
    ))


# The units the engine finds by name rather than through a task force:
# what harvests, what deploys into a construction yard, what a plane
# lands on. A copy of one of those is not the one ``[General]`` names,
# and shutting the original out of a house -- which is what a copy does
# -- would leave that house with no harvester and no way to build a base.
NAMED_BY_THE_ENGINE = (
    'HarvesterUnit', 'BaseUnit', 'PadAircraft', 'SlaveMinerUnit',
    'AmerParaDropInf', 'ParadropInfantry',
)


def engine_named_units():
    """Return the units ``[General]`` names, which must not be copied."""
    from randomizer.ui.cameos import installed_rules_registry

    # The whole ruleset, not the unit roster: [General] is not a
    # TechnoType and the roster does not carry it.
    _superweapons, rules = installed_rules_registry(synchronous=True)
    general = (rules or {}).get('General') or {}
    found = set()
    for key, value in general.items():
        if str(key) not in NAMED_BY_THE_ENGINE:
            continue
        for name in str(value).split(','):
            if name.strip():
                found.add(name.strip().upper())
    return frozenset(found)


def faction_units(country, buff_type):
    """Return the units an army-wide upgrade in this stat reaches.

    The units whose own shelf entry sells that stat, less the stolen-tech
    row and less anything no task force names. Read from the shelf rather
    than assumed, because not every unit has every stat -- a submarine has
    no passenger to carry and a dog has no weapon to reload -- and a buff
    named for a unit that has nowhere to put it is a section in the rules
    and nothing on the field.
    """
    from .ai import fielded_by_ai
    from .ownership import STOLEN_TECH_GROUP
    from .shop import country_upgrades

    fielded = fielded_by_ai()
    spoken_for = engine_named_units()
    return tuple(sorted({
        one.unit for one in country_upgrades(country)
        if one.buff_type == buff_type
        and one.unit != STOLEN_TECH_GROUP
        and one.unit not in spoken_for
        and (not fielded or one.unit in fielded)
    }))


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
        # Two different things, armed two different ways. Every enemy is
        # set the upgrades the Ore a run has earned by now would buy --
        # it does not shop, so they are set for it -- and the tier buys
        # its whole army a stat on top, which an offer asking for a
        # bought-up enemy adds to.
        budget = earned_by(run.battle)
        army_wide = rules.enemy_upgrades + sum(
            one.faction_upgrades for one in ask
        ) + sum(one.enemy_upgrades for one in ask)
        # An armed enemy may not play the ally's country. A copy is gated
        # to a country rather than to a house, so arming that enemy would
        # arm the ally with it -- and the launch, which cannot do that,
        # would send it plain against an offer that promised otherwise and
        # was paid for.
        drawn_from = countries
        if (budget > 0 or army_wide > 0) and ally:
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
                    _country_id(countries, index), budget, generator,
                )
                for index in enemy_countries
            ),
            enemy_faction_upgrades=tuple(
                _faction_upgrades(
                    _country_id(countries, index), army_wide, generator,
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
    # count rather than a list: which stats they are is on the card's
    # pills and in the panel, and what decides a choice is how many.
    # Two different things, so both are said. The tier hands each enemy a
    # few upgrades off its own shelf; an offer that asked for a bought-up
    # enemy buys that army a stat everywhere, for this battle.
    each = 'each ' if enemies > 1 else ''
    carried = max(
        (len(bought) for bought in offer.enemy_bought()), default=0,
    )
    army_wide = max(
        (len(stats) for stats in offer.enemy_faction_bought()), default=0,
    )
    armed = (
        f', {each}carrying {carried} '
        f'{"upgrade" if carried == 1 else "upgrades"}'
        if carried else ''
    )
    if army_wide:
        armed += (
            f', {each}with its whole army bought up '
            f'{army_wide} {"way" if army_wide == 1 else "ways"}'
        )
    reward = (
        f'\n+{offer.bonus_percent}% Ore for taking it'
        if offer.bonus_percent else ''
    )
    stolen = (
        f'\nYou field a {stolen_label(offer.player_stolen)} for this battle'
        if offer.player_stolen else ''
    )
    infiltrated = (
        '\nEvery enemy fields what it could only steal'
        if 'stolen' in set(offer.modifiers) else ''
    )
    return (
        f'{" and ".join(parts)} {"enemy" if enemies == 1 else "enemies"}'
        f'{boost}{armed}, {company}{infiltrated}{stolen}{reward}'
    )


def stolen_label(unit):
    """Return what the game calls one unit, or the ID if it has no name."""
    from randomizer.rewards.catalogue import BUFF_TARGETS

    return str(
        (BUFF_TARGETS.get(str(unit or '').upper()) or {}).get('label') or unit
    )
