"""Typed UI choices and palettes loaded from editable configuration."""

from randomizer.config.static import load_static_config


_UI_CONFIG = load_static_config('ui.json')

DIFFICULTIES = [tuple(item) for item in _UI_CONFIG['difficulties']]
GAME_SPEEDS = [tuple(item) for item in _UI_CONFIG['game_speeds']]
# Missions are balanced and verified at one speed. Leaving it adjustable
# meant a run could be paced differently from the one its rewards and
# enemy scaling were tuned against, so it is fixed here and written to
# both the spawned mission and the in-game options.
LOCKED_GAME_SPEED_VALUE = 4
LOCKED_GAME_SPEED_LABEL = next(
    (name for name, value in GAME_SPEEDS if value == LOCKED_GAME_SPEED_VALUE),
    GAME_SPEEDS[0][0],
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
