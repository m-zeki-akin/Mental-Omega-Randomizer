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
