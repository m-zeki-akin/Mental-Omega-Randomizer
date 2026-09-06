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
# A class belonging to something else. A screen that writes the card's
# own class names is a screen the card cannot be changed without, and one
# that writes the title bar's is a screen reaching outside itself. The
# components own their insides; the shell owns its bands.
BORROWED = re.compile(r"class:\s*'[^']*(card__|titlebar__|panel__)")


def _read(path):
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''


def _views_keep_to_themselves(root):
    """Return the views reaching for something another thing owns.

    Two ways of reaching, both of which were there before this looked:
    writing a component's own class names to get at its insides, and
    naming the shell's bands from inside a screen. A view that does either
    breaks when the thing it borrowed from changes, and nothing says so.
    """
    borrowing = []
    for path in sorted((root / 'views').glob('*.js')):
        text = _read(path)
        for match in BORROWED.finditer(text):
            borrowing.append(f'{path.name}: {match.group(1)}')
        # And the container it draws into is given to it, never found.
        if 'getElementById' in text or 'document.querySelector' in text:
            borrowing.append(f'{path.name}: reaches into the page')
    return borrowing


def _views_register_their_own_name(root):
    """Return the views registering under a name that is not their file's.

    A screen is named once -- by its file, by the table, and by the panel
    it is drawn into. A view registering something else is a tab pointing
    at nothing, or two views quietly sharing one name.
    """
    wrong = []
    for path in sorted((root / 'views').glob('*.js')):
        names = re.findall(r"register\('([a-z]+)'", _read(path))
        if names != [path.stem]:
            wrong.append(f'{path.name}: {names or "registers nothing"}')
    return wrong


def _choice_valid():
    """The interface that opens is the one that was asked for.

    Two ways of asking and one of them wins: a flag is for one run, the
    kept setting is for every other. A setting nobody recognises means the
    old window, because that is the one that can do everything.
    """
    from . import choice

    kept = {'interface': choice.NEW}
    return bool(
        choice.chosen(['--classic'], kept) == choice.CLASSIC
        and choice.chosen(['--interface'], {'interface': choice.CLASSIC})
        == choice.NEW
        and choice.chosen(['--shell'], {}) == choice.NEW
        # A flag among others, and nothing to say about the rest.
        and choice.chosen(['--self-check', '--interface'], {}) == choice.NEW
        and choice.chosen([], kept) == choice.NEW
        and choice.chosen([], {}) == choice.CLASSIC
        and choice.chosen([], {'interface': 'sideways'}) == choice.CLASSIC
        and choice.chosen(None, None) == choice.CLASSIC
    )


def _fallback_valid():
    """An interface that will not open leaves the player with the other one.

    The launcher asks this before it builds a window. A false answer is
    the old window, and a failure has to be a false answer rather than an
    exception: the alternative is an exe that opens nothing.
    """
    import randomizer.shell as package

    from .entry import open_chosen_interface

    opened = []

    def refuse():
        raise RuntimeError('no WebView2 here')

    keep = package.run_shell
    try:
        # Asked for and broken: the old window, quietly.
        package.run_shell = refuse
        failed = open_chosen_interface(['--interface'], warn=False)
        # Asked for and working: this one, and only once.
        package.run_shell = lambda: opened.append(True)
        asked = open_chosen_interface(['--interface'], warn=False)
        # Not asked for: the old window, without the new one being built.
        classic = open_chosen_interface(['--classic'], warn=False)
    finally:
        package.run_shell = keep
    return bool(
        failed is False
        and asked is True
        and classic is False
        and opened == [True]
    )


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

    # Every screen a mode can be drawn as is a screen that exists and is
    # loaded. The page names no screen any more -- it draws what the mode
    # says it has -- so what used to be a check on three lists of tabs is
    # now a check that the table, the files and the page agree.
    from .screens import view_names

    named = set(view_names())
    views = {path.stem for path in (root / 'views').glob('*.js')}
    loaded = set(re.findall(r'src="views/([a-z]+)\.js"', index))
    # A view nobody registers cannot be shown, and app.js is the only
    # thing that shows one.
    registered = set()
    for path in (root / 'views').glob('*.js'):
        registered.update(re.findall(r"register\('([a-z]+)'", _read(path)))
    screens_valid = bool(
        named
        and named <= views
        and named <= loaded
        and named <= registered
        # And nothing loaded that no mode can reach.
        and loaded == named
    )

    borrowing = _views_keep_to_themselves(root)
    misnamed = _views_register_their_own_name(root)

    return {
        'shell_pages_present_valid': present,
        'shell_views_keep_to_themselves_valid': not borrowing,
        'shell_views_are_named_once_valid': not misnamed,
        'shell_interface_choice_valid': _choice_valid(),
        'shell_falls_back_to_the_old_window_valid': _fallback_valid(),
        'shell_tokens_are_the_only_palette_valid': not stray_colours,
        'shell_tokens_are_the_only_scale_valid': not stray_sizes,
        'shell_both_themes_complete_valid': bool(themed and themed <= light),
        'shell_no_markup_parsing_valid': markup_free,
        'shell_components_are_pure_valid': bool(components and components_pure),
        'shell_every_screen_a_mode_names_exists_valid': screens_valid,
        'shell_contract_valid': bool(
            present
            and _choice_valid()
            and _fallback_valid()
            and not stray_colours
            and not stray_sizes
            and markup_free
            and components_pure
            and screens_valid
            and not borrowing
            and not misnamed
        ),
    }
