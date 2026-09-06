"""What a campaign run is set up with, as one table both windows can read.

The three campaign modes -- Classic, Mission List and Grid -- are the same
game in a different order, so almost every setting belongs to all three.
Three belong to Grid alone. That is the whole of the grouping, and it is
written here rather than in a window, because there are two windows now
and a setting described differently in each is a setting a player cannot
ask a question about.

Each row says where the value lives, what it is called, what kind of thing
it is, and what it may be. Nothing here draws anything: a screen turns a
row into a control, and the boundary turns one into a reply.
"""

from randomizer.rewards.arsenal import (
    ARSENAL_COUNT_MAXIMUM,
    ARSENAL_FACTIONS,
    ARSENAL_MODE,
    ARSENAL_POWER_TYPES,
    ARSENAL_TIERS,
    ARSENAL_UNIT_TYPES,
)
from randomizer.rewards.definitions import BUFF_TYPES, MAX_REWARDS_PER_CHECK
from randomizer.rewards.power_buff_definitions import POWER_BUFF_TYPES
from randomizer.rewards.starting import STARTING_REWARD_TYPE_DEFINITIONS

from .config import CAMPAIGN_FILTERS, DIFFICULTIES, GAME_SPEEDS, REWARD_MODES


# A run cannot ask for more missions than the campaign has. The launcher
# counts them per filter; this is the ceiling a control offers, and the
# generator is what refuses an order it cannot fill.
MAXIMUM_MISSION_GOAL = 97

SWITCH = 'switch'
NUMBER = 'number'
CHOICE = 'choice'
TEXT = 'text'
# Several of one catalogue at once, each on or off. A list rather than a
# choice: turning one off is not picking another.
SET = 'set'
# Long enough for any name a player would type, short enough that a
# settings file cannot be filled with one.
MAXIMUM_SEED_LENGTH = 64

# Where a value lives: at the top of the player's settings, or inside the
# generation block that describes how a seed is made.
TOP = ''
GENERATION = 'generation'
# A block inside the generation block. Written as a path because that is
# what it is; nothing here needs a deeper one yet.
ACCESS_LIMITS = 'generation.access_limits'
ARSENAL = 'generation.arsenal'
ARSENAL_POWERS = 'generation.arsenal.power_counts'

# How many starting rewards a control offers. The launcher itself allows
# far more; a spinner that can reach four figures is a spinner nobody
# reaches the end of, and a run that starts with thirty rewards has
# already answered the question the setting was asking.
MAXIMUM_STARTING_REWARDS = 30


def _row(key, label, kind, help_text, *, where=TOP, mode=None, needs=None,
         **rest):
    return {
        'key': key,
        'where': where,
        'label': label,
        'kind': kind,
        'help': help_text,
        # None means every campaign mode. A mode name means that one only,
        # which is how Grid's own three stay off the other two's screen.
        'mode': mode,
        # What has to be true of another setting for this one to mean
        # anything: that setting's full name, and either the value it has
        # to hold or True for "anything at all". A setting that means
        # nothing right now is a setting worth not showing -- the roster
        # sizes are Randomizer Arsenal's alone, a limit's size says
        # nothing while the limit is off, and neither does which kinds a
        # starting reward may be when there are none.
        'needs': needs,
        **rest,
    }


RUN_SETTINGS = (
    _row(
        'seed', 'Seed name', TEXT,
        'Type one to play a run somebody else played. Blank means a new '
        'one is made when the seed is generated.',
        maximum_length=MAXIMUM_SEED_LENGTH,
        # The classic window leaves this box empty while a generated seed
        # stands, so that pressing Generate does not silently replay the
        # run in progress. A second window showing the old seed in it
        # would be the same trap wearing a different face.
        blank_while_generated=True,
    ),
    _row(
        'campaign_filter', 'Campaign', CHOICE,
        'Which side\'s missions the run draws from.',
        choices=list(CAMPAIGN_FILTERS),
    ),
    _row(
        'mission_goal', 'Missions to finish', NUMBER,
        'How many missions a run is. Grid builds its board from this too.',
        minimum=1, maximum=MAXIMUM_MISSION_GOAL, step=1,
    ),
    _row(
        'difficulty', 'Difficulty', CHOICE,
        'What the game itself is played on.',
        choices=[name for name, _value in DIFFICULTIES],
    ),
    _row(
        'game_speed', 'Game speed', CHOICE,
        'The pace a mission starts at.',
        choices=[name for name, _value in GAME_SPEEDS],
    ),
)

REWARD_SETTINGS = (
    _row(
        'reward_mode', 'Reward mode', CHOICE,
        'Standard keeps a unit behind its own faction. Chaos draws from '
        'all four and lets any matching building make what is unlocked. '
        'Randomizer Arsenal gives each mission a mixed roster of its own.',
        where=GENERATION, choices=list(REWARD_MODES),
    ),
    _row(
        'rewards_per_objective', 'Rewards per objective', NUMBER,
        'How many rewards each objective is worth.',
        minimum=1, maximum=MAX_REWARDS_PER_CHECK, step=1,
    ),
    _row(
        'rewards_on_victory_only', 'Rewards only when a mission is finished',
        SWITCH,
        'Otherwise objectives pay as they are met, mid-mission.',
    ),
    _row(
        'use_act_based_reward_multipliers', 'Act-based reward multipliers',
        SWITCH,
        'Later acts pay more than earlier ones.',
    ),
    _row(
        'buff_allied_helpers', 'Buff allied helpers', SWITCH,
        'Whether a mission\'s friendly AI gets the run\'s upgrades too.',
        where=GENERATION,
    ),
    _row(
        'failure_assistance', 'Strengthen failed missions on retry', SWITCH,
        'Each retry makes the units that mission gives you a little better.',
        where=GENERATION,
    ),
)

POOL_SETTINGS = (
    _row(
        'randomize_unit_access', 'Randomize unit access', SWITCH,
        'Lock unearned tech, and hand it back as rewards.',
        where=GENERATION,
    ),
    _row(
        'start_with_tier_one_units', 'Start with basic Tier 1 units', SWITCH,
        'A floor under a run that has unlocked nothing yet.',
        where=GENERATION,
    ),
    _row(
        'start_with_tier_one_defenses', 'Start with basic Tier 1 defences',
        SWITCH,
        'The same floor, for what a base can build to defend itself.',
        where=GENERATION,
    ),
    _row(
        'include_buff_rewards', 'Buff rewards', SWITCH,
        'Rewards that improve a unit rather than unlocking one.',
        where=GENERATION,
    ),
    _row(
        'include_superweapon_rewards', 'Superweapon rewards', SWITCH,
        'The offensive ones.', where=GENERATION,
    ),
    _row(
        'include_secondary_superweapon_rewards', 'Secondary superweapons',
        SWITCH, 'The ones that are not an attack.', where=GENERATION,
    ),
    _row(
        'include_aid_power_rewards', 'Support and aid powers', SWITCH,
        'Powers that help rather than destroy.', where=GENERATION,
    ),
    _row(
        'include_power_buff_rewards', 'Power buff rewards', SWITCH,
        'Rewards that improve a power you already have.', where=GENERATION,
    ),
    _row(
        'include_defensive_buildings', 'Defensive building rewards', SWITCH,
        'Base defences among the buildings a run can unlock.',
        where=GENERATION,
    ),
    _row(
        'include_special_buildings', 'Special economy buildings', SWITCH,
        'The economy buildings a mission map carries.', where=GENERATION,
    ),
    _row(
        'include_special_rewards', 'Campaign-only special rewards', SWITCH,
        'What only one map has, offered as a reward.', where=GENERATION,
    ),
    _row(
        'unlimited_hero_units', 'Unlimited hero units', SWITCH,
        'Lift the build limit on unique units.', where=GENERATION,
    ),
)

LIMIT_SETTINGS = (
    _row(
        'enabled', 'Limit what one reward unlocks', SWITCH,
        'On, a reward opens a few units rather than everything of its kind.',
        where=ACCESS_LIMITS,
    ),
    _row(
        'units', 'Units per reward', NUMBER,
        'How many units one access reward hands over.',
        where=ACCESS_LIMITS, minimum=1, maximum=8, step=1,
        needs=(f'{ACCESS_LIMITS}.enabled', True),
    ),
    _row(
        'powers', 'Powers per reward', NUMBER,
        'The same, for superweapons and support powers.',
        where=ACCESS_LIMITS, minimum=1, maximum=8, step=1,
        needs=(f'{ACCESS_LIMITS}.enabled', True),
    ),
)

BUFF_TYPE_SETTINGS = (
    _row(
        'enabled_buff_types', 'Unit buffs a reward may be', SET,
        'Turn one off and no reward improves a unit that way.',
        where=GENERATION,
        catalogue=[
            {'id': str(entry['id']),
             'label': str(entry.get('setting_label') or entry['id'])}
            for entry in BUFF_TYPES
        ],
    ),
    _row(
        'enabled_power_buff_types', 'Power buffs a reward may be', SET,
        'The same, for what a reward can improve about a power.',
        where=GENERATION,
        catalogue=[
            {'id': str(entry['id']),
             'label': str(entry.get('setting_label') or entry['id'])}
            for entry in POWER_BUFF_TYPES
        ],
    ),
)

STARTING_SETTINGS = (
    _row(
        'starting_reward_count', 'Rewards to start with', NUMBER,
        'Handed over before the first mission, drawn from the kinds below.',
        where=GENERATION, minimum=0, maximum=MAXIMUM_STARTING_REWARDS, step=1,
    ),
    _row(
        'starting_reward_types', 'Kinds a starting reward may be', SET,
        'Turn one off and nothing of that kind is handed over at the start.',
        where=GENERATION,
        catalogue=[
            {'id': str(entry['id']), 'label': str(entry['label'])}
            for entry in STARTING_REWARD_TYPE_DEFINITIONS
        ],
        needs=(f'{GENERATION}.starting_reward_count', True),
    ),
)

ARSENAL_SETTINGS = (
    _row(
        'factions', 'Sides an arsenal draws from', SET,
        'Each mission gets a mixed roster; these are what it is mixed from.',
        where=ARSENAL,
        catalogue=[
            {'id': faction, 'label': faction} for faction in ARSENAL_FACTIONS
        ],
        needs=(f'{GENERATION}.reward_mode', ARSENAL_MODE),
    ),
) + tuple(
    _row(
        unit_type,
        f'{tier.replace("_", " ").title()} {unit_type}',
        NUMBER,
        f'How many {unit_type} of that tier one roster carries.',
        where=f'{ARSENAL}.roster_sizes.{tier}',
        minimum=0, maximum=ARSENAL_COUNT_MAXIMUM, step=1,
        needs=(f'{GENERATION}.reward_mode', ARSENAL_MODE),
    )
    for tier in ARSENAL_TIERS
    for unit_type in ARSENAL_UNIT_TYPES
) + tuple(
    _row(
        power_type, f'{power_type.title()} powers', NUMBER,
        'How many powers of that kind one roster carries.',
        where=ARSENAL_POWERS,
        minimum=0, maximum=ARSENAL_COUNT_MAXIMUM, step=1,
        needs=(f'{GENERATION}.reward_mode', ARSENAL_MODE),
    )
    for power_type in ARSENAL_POWER_TYPES
)

GRID_SETTINGS = (
    _row(
        'grid_two_start_positions', 'Two starting positions', SWITCH,
        'Open the board from two corners rather than one.',
        mode='Grid Mode',
    ),
    _row(
        'hide_locked_grid_missions', 'Hide locked mission names', SWITCH,
        'A locked tile shows a question mark instead of its title.',
        mode='Grid Mode',
    ),
    _row(
        'unlock_all_rewards_after_final_grid_mission',
        'Release every reward at the goal', SWITCH,
        'When the goal mission is done, what is left is handed over.',
        mode='Grid Mode',
    ),
)

SECTIONS = (
    ('Run', RUN_SETTINGS),
    ('Rewards', REWARD_SETTINGS),
    ('Reward pool', POOL_SETTINGS),
    ('Access limits', LIMIT_SETTINGS),
    ('Starting rewards', STARTING_SETTINGS),
    ('Arsenal', ARSENAL_SETTINGS),
    ('What a buff may be', BUFF_TYPE_SETTINGS),
    ('Grid', GRID_SETTINGS),
)

def full_key(row):
    """Return one name for a row, since two blocks both have 'units'."""
    return f'{row["where"]}.{row["key"]}' if row['where'] else row['key']


BY_KEY = {full_key(row): row for _section, rows in SECTIONS for row in rows}


def rows_for(mode):
    """Return the settings one campaign mode shows, section by section."""
    wanted = str(mode or '')
    shown = []
    for name, rows in SECTIONS:
        kept = [row for row in rows if row['mode'] in (None, wanted)]
        if kept:
            shown.append((name, kept))
    return shown
