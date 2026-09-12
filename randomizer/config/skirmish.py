"""Focused schema validation for editable Skirmish Shop balance data.

What is checked is what a run cannot survive being wrong: a price that is
not a number, a tier that fields nobody, a difficulty spelled in a way the
spawn file has never heard of. What is deliberately not checked is whether
the numbers are *good* -- a shelf of thirty and a battle paying one Ore are
a bad run, not a broken one, and someone tuning this file is allowed to
find that out by playing it.
"""


DIFFICULTIES = ('easy', 'medium', 'hard')
# Every flag and count a modifier may carry, beside its key and label.
MODIFIER_NUMBERS = ('percent', 'from_tier', 'extra_enemies',
                    'enemy_upgrades', 'faction_upgrades')
MODIFIER_FLAGS = ('alone', 'mental', 'enemy_stolen')


def _choose(many, size):
    """How many ways ``size`` of ``many`` can be picked."""
    if size > many:
        return 0
    result = 1
    for step in range(size):
        result = result * (many - step) // (step + 1)
    return result


def _counting(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _price(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _named_difficulty(value):
    return isinstance(value, str) and value.strip().lower() in DIFFICULTIES


def _validate_numbers(values, keys, label, path, invalid, *, minimum=0):
    for key in keys:
        value = values.get(key)
        if not _counting(value) or value < minimum:
            invalid(f'Invalid skirmish {label} {key}', path)


def _validate_tier(entry, label, path, invalid):
    if not isinstance(entry, dict):
        invalid(f'Invalid skirmish {label}', path)
        return
    enemies = entry.get('enemies')
    if (
        not isinstance(enemies, list)
        or not enemies
        or not all(_named_difficulty(one) for one in enemies)
    ):
        invalid(f'Invalid skirmish {label} enemies', path)
    if not _named_difficulty(entry.get('challenge')):
        invalid(f'Invalid skirmish {label} challenge difficulty', path)
    if not _counting(entry.get('enemy_upgrades', 0)):
        invalid(f'Invalid skirmish {label} enemy_upgrades', path)
    for flag in ('mental', 'challenge_mental'):
        if not isinstance(entry.get(flag, False), bool):
            invalid(f'Invalid skirmish {label} {flag}', path)


def validate_skirmish_config(sections, path, invalid):
    """Check the balance file a run is tuned by."""
    _validate_numbers(
        sections['economy'],
        ('starting_ore', 'battle_reward', 'reward_per_tier',
         'challenge_reward_multiplier', 'reroll_price'),
        'economy', path, invalid,
    )
    if not _price(sections['economy'].get('stolen_tech_price_per_unit')):
        invalid('Invalid skirmish economy stolen_tech_price_per_unit', path)
    shelf = sections['shelf']
    _validate_numbers(
        shelf,
        ('size', 'cap', 'unit_upgrade_weight', 'power_upgrade_weight',
         'offer_count', 'max_stacked_modifiers'),
        'shelf', path, invalid, minimum=1,
    )
    if _counting(shelf.get('size')) and _counting(shelf.get('cap')):
        # The shelf grows a row a tier up to the cap, so a cap below the
        # opening size is a shelf that shrinks as a run gets richer.
        if shelf['cap'] < shelf['size']:
            invalid('Skirmish shelf cap is below its opening size', path)

    prices = sections['prices']
    if not _counting(prices.get('default')) or prices['default'] < 1:
        invalid('Invalid skirmish default price', path)
    for table in ('unit', 'power'):
        values = prices.get(table)
        if not isinstance(values, dict) or not values:
            invalid(f'Invalid skirmish {table} price table', path)
            continue
        for buff_type, price in values.items():
            if (
                not isinstance(buff_type, str) or not buff_type
                or not _counting(price) or price < 1
            ):
                invalid(f'Invalid skirmish {table} price {buff_type!r}', path)
    unsold = prices.get('unsold')
    if not isinstance(unsold, list) or not all(
        isinstance(one, str) and one for one in unsold
    ):
        invalid('Invalid skirmish unsold buff list', path)

    run = sections['run']
    lengths = run.get('tier_lengths')
    if (
        not isinstance(lengths, list) or not lengths
        or not all(_counting(one) and one > 0 for one in lengths)
    ):
        invalid('Invalid skirmish tier_lengths', path)
    _validate_numbers(
        run, ('lives', 'first_walk_challenges'),
        'run', path, invalid, minimum=1,
    )

    tiers = sections['tiers']
    _validate_tier(tiers.get('warmup'), 'warmup tier', path, invalid)
    ladder = tiers.get('ladder')
    if not isinstance(ladder, list) or not ladder:
        invalid('Skirmish tier ladder cannot be empty', path)
        ladder = []
    for index, entry in enumerate(ladder):
        _validate_tier(entry, f'tier {index + 1}', path, invalid)

    keys = []
    for entry in sections['modifiers']:
        if not isinstance(entry, dict):
            invalid('Invalid skirmish modifier', path)
            continue
        key = entry.get('key')
        if not isinstance(key, str) or not key:
            invalid('Invalid skirmish modifier key', path)
        else:
            keys.append(key)
        if not isinstance(entry.get('label'), str) or not entry['label']:
            invalid(f'Invalid skirmish modifier label for {key!r}', path)
        if not _counting(entry.get('percent')) or entry['percent'] < 1:
            invalid(f'Invalid skirmish modifier percent for {key!r}', path)
        _validate_numbers(
            entry, [one for one in MODIFIER_NUMBERS if one in entry],
            f'modifier {key!r}', path, invalid,
        )
        for flag in MODIFIER_FLAGS:
            if not isinstance(entry.get(flag, False), bool):
                invalid(f'Invalid skirmish modifier {flag} for {key!r}', path)
    if len(keys) != len(set(keys)):
        invalid('Duplicate skirmish modifier key', path)

    # A table is the plain battle and then combinations of what the
    # opening tier allows, none repeated. Asking for more offers than
    # there are combinations is asking for a table that cannot be dealt.
    opening = [
        one for one in sections['modifiers']
        if isinstance(one, dict) and int(one.get('from_tier', 1) or 1) <= 1
    ]
    stacked = shelf.get('max_stacked_modifiers')
    offers = shelf.get('offer_count')
    if _counting(stacked) and _counting(offers) and stacked > 0:
        combinations = 1
        for size in range(1, stacked + 1):
            combinations += _choose(len(opening), size)
        if offers > combinations:
            invalid(
                f'Skirmish table of {offers} offers, but the opening tier '
                f'has only {combinations} to fill it with',
                path,
            )

    enemy = sections['enemy']
    if not _named_difficulty(enemy.get('ally_difficulty')):
        invalid('Invalid skirmish ally difficulty', path)
    unbought = enemy.get('unbought_buffs')
    if not isinstance(unbought, list) or not all(
        isinstance(one, str) and one for one in unbought
    ):
        invalid('Invalid skirmish unbought buff list', path)
    stats = enemy.get('faction_stats')
    if not isinstance(stats, dict) or not stats or not all(
        isinstance(stat, str) and stat and isinstance(label, str) and label
        for stat, label in stats.items()
    ):
        invalid('Invalid skirmish faction stats', path)
    elif set(stats) & set(unbought or ()):
        # An army-wide stat the enemy is never bought is a contradiction
        # the draw would resolve silently by never picking it.
        invalid('A skirmish faction stat is also an unbought buff', path)
