"""Typed UI choices and palettes loaded from editable configuration."""

from randomizer.config.static import load_static_config


_UI_CONFIG = load_static_config('ui.json')

DIFFICULTIES = [tuple(item) for item in _UI_CONFIG['difficulties']]
# The number the game writes is not the number it shows. Mental Omega's
# own client lists "6 Fastest" first and writes 0 for it, so a lower value
# is a faster game: the client's skirmish default, cmbSkirmishGameSpeedCap=1
# in Client/SkirmishSettings.ini, is the speed a player sees as 5. The
# labels here say what the player sees and the value is what the file gets.
GAME_SPEEDS = [tuple(item) for item in _UI_CONFIG['game_speeds']]
# Missions are balanced and verified at one speed. Leaving it adjustable
# meant a run could be paced differently from the one its rewards and
# enemy scaling were tuned against, so it is fixed and written to both the
# spawned mission and the in-game options. Which speed that is belongs in
# the configuration: a slower game is an easier game, so this is a dial the
# difficulty will want, not a constant to bury in code.
LOCKED_GAME_SPEED_VALUE = int(_UI_CONFIG['locked_game_speed'])
LOCKED_GAME_SPEED_LABEL = next(
    (name for name, value in GAME_SPEEDS if value == LOCKED_GAME_SPEED_VALUE),
    GAME_SPEEDS[0][0],
)
# Units a skirmish does not sell upgrades for, whatever the rules say a
# country could field. Mental Omega's own gates put some of them out of a
# skirmish's reach in practice -- the Cyborg Commando wants all four sides'
# barracks and all four stolen techs -- and some are simply not what this
# mode is about.
SKIRMISH_EXCLUDED_UNITS = frozenset(
    str(unit).upper() for unit in _UI_CONFIG['skirmish_excluded_units']
)
CAMPAIGN_FILTERS = list(_UI_CONFIG['campaign_filters'])
REWARD_MODES = list(_UI_CONFIG['reward_modes'])
PROGRESSION_MODES = list(_UI_CONFIG['progression_modes'])
DEFAULT_PROGRESSION_MODE = str(_UI_CONFIG['default_progression_mode'])
# The five modes are two kinds of game. What is stored for a workspace is
# still one of the five; the grouping is how they are offered, so that a
# player picks a kind and then which one of it, rather than reading a list
# of five things with nothing in common.
MODE_FAMILIES = [
    {
        'name': str(family['name']),
        'description': str(family['description']),
        'modes': [
            {'mode': str(entry['mode']), 'label': str(entry['label'])}
            for entry in family['modes']
        ],
    }
    for family in _UI_CONFIG['mode_families']
]


def mode_family_names():
    """Return the kinds of game, in the order they are offered."""
    return [family['name'] for family in MODE_FAMILIES]


def mode_family(mode):
    """Return the kind of game a mode is one of, or the first kind."""
    wanted = str(mode or '')
    for family in MODE_FAMILIES:
        if any(entry['mode'] == wanted for entry in family['modes']):
            return family['name']
    return MODE_FAMILIES[0]['name']


def mode_label(mode):
    """Return what a mode is called inside its own kind of game."""
    wanted = str(mode or '')
    for family in MODE_FAMILIES:
        for entry in family['modes']:
            if entry['mode'] == wanted:
                return entry['label']
    return wanted


def modes_in_family(name):
    """Return the modes of one kind of game, in its own order."""
    for family in MODE_FAMILIES:
        if family['name'] == str(name or ''):
            return [entry['mode'] for entry in family['modes']]
    return []


def labels_in_family(name):
    """Return what one kind of game calls each of its modes.

    What a control offers, where the modes themselves are what a
    workspace stores. Inside the Roguelike kind the two are called
    Campaign and Skirmish; a dropdown offering "Shop Mode" and "Skirmish
    Shop" beside a kind called Roguelike is three names for two things.
    """
    return [mode_label(mode) for mode in modes_in_family(name)]


def mode_by_label(name, label):
    """Return the mode one kind of game calls by that name, if it has one."""
    wanted = str(label or '')
    for mode in modes_in_family(name):
        if mode_label(mode) == wanted:
            return mode
    return ''


def family_description(name):
    """Return what a kind of game is, for the control that offers it."""
    for family in MODE_FAMILIES:
        if family['name'] == str(name or ''):
            return family['description']
    return ''
PLAYER_COLORS = list(_UI_CONFIG['player_colors'])
RAINBOWIZER_COLORS = list(_UI_CONFIG['rainbowizer_colors'])

# Voice tags are one source of truth. Dict insertion order controls menu order;
# adding/removing/renaming one entry updates both choices and map tag lookup.
EVA_VOICE_TAGS = dict(_UI_CONFIG['eva_voice_tags'])
EVA_VOICE_CHOICES = ['Mission default', *EVA_VOICE_TAGS, 'Random']
EVA_APPEARANCE_PROFILES = dict(
    _UI_CONFIG.get('eva_appearance_profiles', {})
)

REWARDS_PER_CHECK_MAXIMUM_MESSAGE = str(
    _UI_CONFIG['rewards_per_check_messages']['maximum']
)
REWARDS_PER_CHECK_MESSAGE_THRESHOLDS = tuple(
    (int(threshold), str(message))
    for threshold, message in _UI_CONFIG['rewards_per_check_messages']['thresholds']
)

FACTION_TILE_COLORS = dict(_UI_CONFIG['faction_tile_colors'])
LIGHT_UI_PALETTE = dict(_UI_CONFIG['light_palette'])
DARK_UI_PALETTE = dict(_UI_CONFIG['dark_palette'])
