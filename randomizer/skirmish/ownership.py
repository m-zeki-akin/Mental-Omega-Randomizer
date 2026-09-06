"""What one country can actually build.

A side is not an army. All three Allied countries share a side and field
different rosters: the Hailstorm needs ``GASCPF``, the Pacific Front's tier
two building, and a United States player never sees one. The Armadillo is
owned by all three Soviet countries and then handed to China alone by
``RequiredHouses=Chinese``. Selling a player upgrades for units their
country cannot build is selling them nothing.

Two gates decide it, and both have to be read:

**Ownership.** ``RequiredHouses`` when present, otherwise ``Owner``, minus
anything in ``ForbiddenHouses``; ``FactoryOwners`` narrows it again, because
a type only that country's factory may produce is only that country's.

**Tech level.** A match is played to a cap -- ``TechLevel`` in spawn.ini,
10 by default -- and a type above it is not built in one. This is what
separates the campaign units from the rest: the Future Tank X-0, Sammy
Stallion and four hundred others sit at level 11, with no owner and no
prerequisite, because a mission hands them over rather than a factory. A
level of -1 is never built either.

The cap applies to the type being sold and to nothing it stands on. A
Construction Yard is ``TechLevel=-1`` because an MCV deploys into one
rather than a sidebar producing it, so a prerequisite chain that read the
cap would refuse every building in the game.

**Prerequisites.** A prerequisite names a building, or a group of them --
``ALLT2`` is ``GAMERC,GASCEA,GASCPF``, one per Allied country -- and a group
is satisfied by any one member. So the tier-two chain gates a whole tier of
units per country without any of them naming a country themselves. Groups
come from ``[GenericPrerequisites]`` and from ``[General]``'s own
``PrerequisitePower`` and friends, read from the installation rather than
listed here: a submod's groups are its own.

A prerequisite this cannot resolve counts as satisfied. Over-filtering
would quietly empty a faction's shelf, and a shelf that is missing an
upgrade is worse than one that offers a doubtful one.
"""

from functools import lru_cache


OWNERSHIP_DEPTH = 6
# ``POWER`` in a prerequisite is ``[General] PrerequisitePower``. The engine
# reads a handful of these by name; the rest of a prerequisite is either a
# generic group or a building.
GENERAL_PREREQUISITES = {
    'POWER': 'PrerequisitePower',
    'FACTORY': 'PrerequisiteFactory',
    'BARRACKS': 'PrerequisiteBarracks',
    'RADAR': 'PrerequisiteRadar',
    'TECH': 'PrerequisiteTech',
    'PROC': 'PrerequisiteProc',
    'PROCALTERNATE': 'PrerequisiteProcAlternate',
}
NOTHING = frozenset({'', 'none', '<none>'})


def _items(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def _value(values, key):
    for name, value in (values or {}).items():
        if str(name).lower() == key.lower():
            return value
    return ''


def owns(values, country):
    """Whether a house of this country may own what this section describes."""
    if not values:
        return False
    wanted = str(country).lower()
    forbidden = [name.lower() for name in _items(_value(values, 'ForbiddenHouses'))]
    if wanted in forbidden:
        return False
    required = [
        name.lower() for name in _items(_value(values, 'RequiredHouses'))
        if name.lower() not in NOTHING
    ]
    if required:
        if wanted not in required:
            return False
    else:
        owners = [name.lower() for name in _items(_value(values, 'Owner'))]
        if owners and wanted not in owners:
            return False
    factories = [
        name.lower() for name in _items(_value(values, 'FactoryOwners'))
        if name.lower() not in NOTHING
    ]
    if factories and wanted not in factories:
        return False
    return True


def _groups(rules):
    """Return every prerequisite name that stands for a list of buildings."""
    groups = {
        str(name).upper(): _items(value)
        for name, value in (rules.get('GenericPrerequisites') or {}).items()
    }
    general = rules.get('General') or {}
    for token, key in GENERAL_PREREQUISITES.items():
        members = _items(_value(general, key))
        if members:
            groups.setdefault(token, members)
    return groups


def within_tech_level(values, cap):
    """Whether this type is reachable in a match played to ``cap``."""
    raw = str(_value(values, 'TechLevel')).strip()
    if not raw:
        return True
    try:
        level = int(float(raw))
    except ValueError:
        return True
    if level < 0:
        # Never built. The rules use this for clones, AI-only variants and
        # everything else the sidebar is not meant to offer.
        return False
    return level <= cap


def _buildable(unit, country, rules, groups, seen, depth):
    """Whether this country can have this type, prerequisites and all.

    Ownership only, all the way down. The tech level belongs to the type
    being sold and not to what it stands on: a Construction Yard is
    ``TechLevel=-1`` because nobody builds one from a sidebar -- an MCV
    deploys into it -- and a chain that refused it would refuse every
    building in the game.
    """
    unit = str(unit).upper()
    if unit in seen or depth <= 0:
        # A prerequisite loop, or a chain too deep to be worth following.
        # Counting it as satisfied keeps a doubtful upgrade on the shelf
        # rather than taking a real one off.
        return True
    values = rules.get(unit)
    if not values:
        return True
    if not owns(values, country):
        return False
    seen = seen | {unit}
    for token in _items(_value(values, 'Prerequisite')):
        token = token.upper()
        members = groups.get(token, [token])
        if not any(
            _buildable(member, country, rules, groups, seen, depth - 1)
            for member in members
        ):
            return False
    return True


def match_tech_level():
    """Return the tech level a skirmish is played to."""
    from .spawn import DEFAULT_MATCH_OPTIONS

    try:
        return int(str(DEFAULT_MATCH_OPTIONS.get('TechLevel', 10)).strip())
    except ValueError:
        return 10


@lru_cache(maxsize=32)
def buildable_units(country, tech_level=None):
    """Return every TechnoType id this country can put on the field."""
    from randomizer.ui.cameos import installed_rules_registry

    cap = match_tech_level() if tech_level is None else int(tech_level)
    _superweapons, rules = installed_rules_registry(synchronous=True)
    if not rules:
        return frozenset()
    upper = {str(name).upper(): values for name, values in rules.items()}
    groups = _groups(rules)
    listed = set()
    for section in (
        'InfantryTypes', 'VehicleTypes', 'AircraftTypes', 'BuildingTypes',
    ):
        listed.update(
            str(value).upper() for value in (rules.get(section) or {}).values()
        )
    return frozenset(
        unit for unit in listed
        if within_tech_level(upper.get(unit), cap)
        and _buildable(unit, country, upper, groups, frozenset(), OWNERSHIP_DEPTH)
    )


# One purchase for all of them rather than one per unit. A stolen-tech unit
# is not something a run fields on purpose: it arrives only if the player
# infiltrates the right building, and which one they get is not theirs to
# choose. Pricing sixteen separate upgrades for units that may never appear
# would be selling a lottery ticket sixteen times.
STOLEN_TECH_GROUP = '@STOLENTECH'
STOLEN_TECH_KEY = 'prerequisite.stolentechs'


@lru_cache(maxsize=1)
def stolen_tech_sections():
    """Return the option file that defines the stolen-tech units.

    Not the rules: what makes these units exist at all is the Stolen Tech
    game option, and its file carries both the country lists and the
    ``Prerequisite.StolenTechs`` that gate them.
    """
    from .options import option_ini_path, read_ini_sections

    path = option_ini_path('StolenTech')
    if path is None:
        return {}
    return {
        str(name).upper(): values
        for name, values in read_ini_sections(path).items()
    }


@lru_cache(maxsize=16)
def stolen_tech_units(country):
    """Return the units this country reaches only by infiltrating somebody."""
    sections = stolen_tech_sections()
    if not sections:
        return ()
    from randomizer.rewards.catalogue import BUFF_TARGETS

    fielded = buildable_units(country)
    return tuple(sorted(
        unit for unit, values in sections.items()
        if any(str(key).lower() == STOLEN_TECH_KEY for key in values)
        and unit in BUFF_TARGETS
        and owns(values, country)
        # The option file describes them; the rules still say how far up the
        # tech tree they sit, and a match has a ceiling.
        and unit in fielded
    ))


def expand_group(unit, country):
    """Return the units one shelf row stands for."""
    if str(unit).upper() == STOLEN_TECH_GROUP:
        return stolen_tech_units(country)
    return (str(unit).upper(),)


@lru_cache(maxsize=16)
def country_faction(country):
    """Return what Mental Omega calls this country's faction."""
    from .factions import skirmish_countries

    for entry in skirmish_countries():
        if entry.country_id.lower() == str(country or '').lower():
            return entry.side
    return ''


def country_builds(unit, country, tech_level=None):
    """Whether one country can build one unit, prerequisites and all."""
    return str(unit).upper() in buildable_units(country, tech_level)
