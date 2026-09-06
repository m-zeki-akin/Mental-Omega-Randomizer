"""Assert the interface stays the thing it was designed as.

A design system decays one hardcoded colour at a time. Nothing here looks
at how the launcher looks -- that is a person's job -- but these are the
promises that keep looking at it worth doing: one place decides a value,
components do not reach past themselves, and text from the game is never
parsed as markup.
"""

import re
from pathlib import Path


def web_root():
    from .host import web_root as resolved

    return resolved()


# A colour written anywhere but the token file is a colour that will not
# follow a theme. Sizes are the same argument one step down.
HEX_COLOUR = re.compile(r'#[0-9a-fA-F]{3,8}\b')
RAW_PIXELS = re.compile(r':\s*-?\d+px')
# What a value may still be written as, because a token for it would be a
# token nobody could name: hairlines, zero, and the shapes of a scrollbar.
PIXEL_EXCEPTIONS = re.compile(r':\s*-?(0|1|2|3|10)px')
# Writing markup, rather than mentioning it.
MARKUP_WRITE = re.compile(r'\.(inner|outer)HTML\s*=')


def _read(path):
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''


def validate_shell_contract():
    """Return one row per promise the interface makes about itself."""
    root = web_root()
    if not root.is_dir():
        return {
            'shell_pages_present_valid': False,
            'shell_contract_valid': False,
        }

    styles = sorted((root / 'styles').glob('*.css'))
    scripts = sorted(root.rglob('*.js'))
    tokens = _read(root / 'styles' / 'tokens.css')
    index = _read(root / 'index.html')

    present = bool(
        (root / 'index.html').is_file()
        and tokens
        and len(styles) >= 3
        and len(scripts) >= 4
    )

    # Every colour is decided once. The token file is the one place a hex
    # value belongs; anywhere else it is a value that will not follow a
    # theme, and the launcher has two.
    stray_colours = [
        path.name for path in styles
        if path.name != 'tokens.css' and HEX_COLOUR.search(_read(path))
    ]
    # ...and the same for sizes, minus the handful a token would only
    # obscure.
    stray_sizes = []
    for path in styles:
        if path.name == 'tokens.css':
            continue
        for match in RAW_PIXELS.finditer(_read(path)):
            if not PIXEL_EXCEPTIONS.match(match.group()):
                stray_sizes.append(f'{path.name}: {match.group().strip()}')

    # Both themes define every token, or a screen changes theme and keeps
    # one colour from the other.
    dark = set(re.findall(r'--([a-z0-9-]+):', tokens.split('[data-theme')[0]))
    light = set(re.findall(
        r'--([a-z0-9-]+):', tokens.split('[data-theme="light"]')[-1]
    ))
    # The light theme restates what changes, not what cannot: type, space
    # and shape are the same in daylight.
    themed = {
        name for name in dark
        if name.startswith(('bg', 'surface', 'line', 'text', 'ore', 'accent',
                            'danger', 'success', 'warn', 'skill', 'shadow'))
    }

    # Text from the game -- a map name a player downloaded, a unit name a
    # submod wrote -- is put in as text. Nothing builds an element by
    # parsing a string.
    # An assignment, not the word: the module that refuses to parse
    # markup says so by naming it.
    markup_free = not any(
        MARKUP_WRITE.search(_read(path)) for path in scripts
    )

    # A component takes data and returns an element. One that asks the
    # launcher for something is a component that cannot be reused.
    components = sorted((root / 'components').glob('*.js'))
    components_pure = not any(
        'pywebview' in _read(path) or "from '../app.js'" in _read(path)
        for path in components
    )

    # Every screen the shell offers a tab for is a screen that exists.
    tabs = set(re.findall(r'data-view="([a-z]+)"', index))
    views = {path.stem for path in (root / 'views').glob('*.js')}
    panels = set(re.findall(r'id="view-([a-z]+)"', index))

    return {
        'shell_pages_present_valid': present,
        'shell_tokens_are_the_only_palette_valid': not stray_colours,
        'shell_tokens_are_the_only_scale_valid': not stray_sizes,
        'shell_both_themes_complete_valid': bool(themed and themed <= light),
        'shell_no_markup_parsing_valid': markup_free,
        'shell_components_are_pure_valid': bool(components and components_pure),
        'shell_every_tab_has_a_screen_valid': bool(
            tabs and tabs == views and tabs == panels
        ),
        'shell_contract_valid': bool(
            present
            and not stray_colours
            and not stray_sizes
            and markup_free
            and components_pure
            and tabs
            and tabs == views == panels
        ),
    }
