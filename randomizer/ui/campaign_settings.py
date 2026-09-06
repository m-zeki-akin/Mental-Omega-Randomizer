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

from randomizer.rewards.definitions import MAX_REWARDS_PER_CHECK

from .config import CAMPAIGN_FILTERS, DIFFICULTIES, GAME_SPEEDS


# A run cannot ask for more missions than the campaign has. The launcher
# counts them per filter; this is the ceiling a control offers, and the
# generator is what refuses an order it cannot fill.
MAXIMUM_MISSION_GOAL = 97

SWITCH = 'switch'
NUMBER = 'number'
CHOICE = 'choice'
TEXT = 'text'
# Long enough for any name a player would type, short enough that a
# settings file cannot be filled with one.
MAXIMUM_SEED_LENGTH = 64

# Where a value lives: at the top of the player's settings, or inside the
# generation block that describes how a seed is made.
TOP = ''
GENERATION = 'generation'


def _row(key, label, kind, help_text, *, where=TOP, mode=None, **rest):
    return {
        'key': key,
        'where': where,
        'label': label,
        'kind': kind,
        'help': help_text,
        # None means every campaign mode. A mode name means that one only,
        # which is how Grid's own three stay off the other two's screen.
        'mode': mode,
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
    ('Grid', GRID_SETTINGS),
)

BY_KEY = {row['key']: row for section, rows in SECTIONS for row in rows}


def rows_for(mode):
    """Return the settings one campaign mode shows, section by section."""
    wanted = str(mode or '')
    shown = []
    for name, rows in SECTIONS:
        kept = [row for row in rows if row['mode'] in (None, wanted)]
        if kept:
            shown.append((name, kept))
    return shown
