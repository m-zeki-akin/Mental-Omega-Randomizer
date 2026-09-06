"""The countries a skirmish can seat, in the order the engine indexes them.

A spawn file names a country by its position in ``[Countries]``, not by its
name, so the order in the installed rules is the only authority. This reads
it from there and checks it against what stock Mental Omega ships: a submod
that reorders the list still plays, and one that renames a country still
plays, but a launcher that assumed position 6 was Epsilon while the rules
said otherwise would put the player in the wrong army with no error at all.
"""

from dataclasses import dataclass
from functools import lru_cache
import re


# The stock order. Not used to build the line-up -- the installed rules are --
# but a mismatch against it is worth reporting.
EXPECTED_COUNTRIES = (
    'UnitedStates', 'Europeans', 'Pacific',      # Allies
    'USSR', 'Latin', 'Chinese',                  # Soviets
    'PsiCorps', 'ScorpionCell', 'Headquaters',   # Epsilon
    'Guild1', 'Guild2', 'Guild3',                # Foehn
)

# The engine's side ids, and what Mental Omega calls them.
SKIRMISH_SIDES = {
    'GDI': 'Allies',
    'Nod': 'Soviets',
    'ThirdSide': 'Epsilon',
    'FourthSide': 'Foehn',
}

# Two UINames the mod spells in ways that do not survive being split into
# words. Everything else reads correctly straight off the rules.
COUNTRY_LABEL_FIXES = {
    'Confederationz': 'Latin Confederation',
    'Headquaters': 'Epsilon Headquarters',
}


@dataclass(frozen=True)
class SkirmishCountry:
    index: int
    country_id: str
    side: str
    label: str
    # What the rules call the side, as against what Mental Omega calls it.
    # The AI file numbers its sides by this list's order, so the engine's
    # own id is what a lookup there has to start from.
    side_id: str = ''

    @property
    def display(self):
        return f'{self.side} — {self.label}'


def _label(ui_name, country_id):
    """Turn ``NAME:PacificFront`` into ``Pacific Front``."""
    name = str(ui_name or '').split(':', 1)[-1].strip() or country_id
    name = COUNTRY_LABEL_FIXES.get(name, name)
    if ' ' in name:
        return name
    spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
    return spaced


def _section_value(section, key):
    for name, value in (section or {}).items():
        if str(name).lower() == key:
            return str(value)
    return ''


@lru_cache(maxsize=1)
def skirmish_countries():
    """Return the playable countries, in engine order.

    ``Multiplay`` is what separates a country a skirmish can seat from the
    civilian and special houses that share the same list.
    """
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, sections = installed_rules_registry(synchronous=True)
    countries = sections.get('Countries') or {}
    result = []
    for key in sorted(countries, key=lambda item: int(item)):
        country_id = str(countries[key]).strip()
        section = sections.get(country_id) or {}
        if _section_value(section, 'multiplay').strip().lower() not in {
            'yes', 'true', '1',
        }:
            continue
        side = _section_value(section, 'side')
        result.append(SkirmishCountry(
            index=int(key),
            country_id=country_id,
            side=SKIRMISH_SIDES.get(side, side or 'Unknown'),
            label=_label(_section_value(section, 'uiname'), country_id),
            side_id=side,
        ))
    return tuple(result)


def countries_by_side():
    """Return ``{side: (country, ...)}`` in engine order."""
    grouped = {}
    for country in skirmish_countries():
        grouped.setdefault(country.side, []).append(country)
    return {side: tuple(values) for side, values in grouped.items()}


def country_by_index(index):
    for country in skirmish_countries():
        if country.index == int(index):
            return country
    return None


def validate_installed_countries():
    """Report how the installed country list compares with stock."""
    countries = skirmish_countries()
    installed = tuple(country.country_id for country in countries)
    matched = tuple(
        country_id for position, country_id in enumerate(installed)
        if position < len(EXPECTED_COUNTRIES)
        and country_id == EXPECTED_COUNTRIES[position]
    )
    return {
        'playable_countries': len(countries),
        'stock_order_matches': len(matched),
        'sides': sorted({country.side for country in countries}),
        'moved_or_renamed': [
            f'{position}: {country_id}'
            for position, country_id in enumerate(installed)
            if position >= len(EXPECTED_COUNTRIES)
            or country_id != EXPECTED_COUNTRIES[position]
        ],
    }
