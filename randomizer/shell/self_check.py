"""Assert the interface stays the thing it was designed as.

A design system decays one hardcoded colour at a time. Nothing here looks
at how the launcher looks -- that is a person's job -- but these are the
promises that keep looking at it worth doing: one place decides a value,
components do not reach past themselves, and text from the game is never
parsed as markup.

And one promise about the other side of the glass, because a screen names
the launcher's actions in strings: every name a screen asks for is a name
the launcher answers to. Nothing else would notice a typo until a player
pressed the button under it.
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
# What a screen asks the launcher for. Both spellings: a screen reads with
# one and acts with the other, and both name an action.
ASKED = re.compile(r"\b(?:call|act)\(\s*'([a-z_]+\.[a-z_]+)'")
# The one place a screen changes anything, and the flag that keeps a
# second press out while the first is still landing.
ACTING = re.compile(
    r'export async function act\([^)]*\)\s*\{(?P<body>.*?)\n\}', re.S
)
FLAGS = re.compile(r'\blet\s+(\w+)\s*=\s*false;')


def _presses_wait_their_turn(root):
    """Return what is wrong with the gate on a screen's own presses.

    Every change a screen makes goes through one function: it sends the
    change, waits for the launcher, and redraws from the answer. A second
    press arriving before that answer decides from a screen that is
    already out of date -- and where a control sends a whole list rather
    than the one thing that moved, that is a change quietly lost. Adding
    two units to an exclusion list quickly would send the second list
    without the first unit in it, and the launcher would keep what it was
    told.

    So a press while one is landing is turned away, and the flag that
    does it is cleared however the press ends. Both halves are checked:
    the launcher itself running one action at a time cannot help here,
    because the second press is not early, it is wrong.
    """
    text = _read(root / 'app.js')
    found = ACTING.search(text)
    if not found:
        return ['app.js: no act() to gate']
    body = found.group('body')
    flags = [name for name in FLAGS.findall(text) if f'{name} = true' in body]
    wrong = []
    if not flags:
        wrong.append('app.js: act() turns no second press away')
    elif not any(f'if ({name})' in body for name in flags):
        wrong.append('app.js: act() sets a flag it never reads')
    if 'finally' not in body:
        wrong.append('app.js: act() can leave the gate shut')
    return wrong


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


def _actions_the_screens_ask_for(root):
    """Return the actions the interface asks for that do not exist.

    A name is the whole of the boundary. A screen asking for
    ``skirmish.gve_up`` is not a syntax error and not a failed import; it
    is a button that tells the player the launcher refused, and only when
    they press it. The same goes for a name that was right until an action
    was renamed on the other side.

    So the names are read out of the screens and looked up. Statically,
    because the alternative is pressing every button in every mode.
    """
    from randomizer.api import launcher, skirmish  # noqa: F401  -- register
    from randomizer.api.contract import actions

    known = set(actions())
    missing = []
    for path in sorted(root.rglob('*.js')):
        for name in ASKED.findall(_read(path)):
            if name not in known:
                missing.append(f'{path.name}: {name}')
    return missing


def _failure_reported_valid():
    """An interface that will not open says so rather than raising.

    The launcher's entry point asks this and exits on a false answer.
    There is no other window to fall back to, so what matters is that a
    failure is an answer -- logged, and shown -- and not an exception
    that leaves an exe opening nothing and saying nothing.
    """
    import randomizer.shell as package

    from . import entry

    opened = []
    warned = []

    def refuse():
        raise RuntimeError('no WebView2 here')

    def ask(**how):
        # A row that raised where the launcher would have raised would
        # take the whole report down with it, which is the failure it is
        # here to find. It is an answer either way.
        try:
            return entry.open_interface(**how)
        except Exception:
            return 'raised'

    keep_shell, keep_warn = package.run_shell, entry.warn
    try:
        # Broken, with the self-check's silence on: a false answer and
        # no dialog.
        package.run_shell = refuse
        entry.warn = lambda title, text: warned.append(title)
        failed = ask(warn_player=False)
        # Broken, as the player would see it: the same answer, said.
        told = ask()
        # Working: a true answer, and the interface built once.
        package.run_shell = lambda: opened.append(True)
        worked = ask()
    finally:
        package.run_shell, entry.warn = keep_shell, keep_warn
    return bool(
        failed is False
        and told is False
        and worked is True
        and opened == [True]
        and len(warned) == 1
    )


def _only_interface_valid():
    """There is one interface, and no code path to another.

    The old window was Tk; the check is that nothing under the package
    asks for it. One module is allowed to: the campaign controllers'
    import hub still names tkinter for the dead callbacks the headless
    generator never reaches, and that allowance is written here so its
    removal is a row turning stricter rather than a surprise.
    """
    from pathlib import Path

    package = Path(__file__).resolve().parent.parent
    allowed = {'application/_dependencies.py'}
    naming = {
        path.relative_to(package).as_posix()
        for path in package.rglob('*.py')
        if 'tkinter' in _read(path)
        # This module names it in prose, above, and the api sweep names
        # it as a word to refuse.
        and path.name != 'self_check.py'
    }
    return bool(naming <= allowed)


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

    # Hiding a thing hides it, whatever that thing is laid out as.
    #
    # The browser answers `hidden` with `display: none` and any rule of
    # ours that sets a display outranks it, so a component laid out as a
    # grid stayed on screen after being hidden -- the search list under
    # the exclusion boxes was permanently down, and the code putting it
    # away on every blur did nothing at all. Stated once, globally, and
    # checked for two things: that the statement is there, and that
    # nobody has gone back to patching it one class at a time, which is
    # the shape that hid the bug for as long as it did.
    css = ''.join(_read(path) for path in styles)
    hides = re.search(
        r'(^|[\s}])\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important',
        css,
    )
    patched = re.findall(r'\.[a-z-]+\[hidden\]', css)
    hidden_valid = bool(hides and not patched)

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

    # Every mode the launcher lists is drawn here, with screens of its
    # own: there is no other window now, so a mode without a row would be
    # a mode that cannot be played.
    from randomizer.ui.config import PROGRESSION_MODES

    from .screens import BY_MODE

    every_mode_drawn_valid = bool(
        set(PROGRESSION_MODES) == set(BY_MODE)
        and all(BY_MODE[mode] for mode in PROGRESSION_MODES)
    )

    # The control is two: a kind of game, then one of that kind. Which
    # means every mode has to be one kind exactly -- a mode in neither
    # cannot be reached from the control at all, and a mode in two would
    # be reachable under a kind it is not.
    from .screens import families, family, label, modes, modes_in

    grouped = [
        entry['mode'] for kind in families() for entry in kind['modes']
    ]
    families_valid = bool(
        families()
        and all(kind['modes'] and kind['description'] for kind in families())
        and sorted(grouped) == sorted(modes())
        and len(grouped) == len(set(grouped))
        and all(
            label(mode) and mode in modes_in(family(mode))
            for mode in modes()
        )
    )

    borrowing = _views_keep_to_themselves(root)
    misnamed = _views_register_their_own_name(root)
    unanswered = _actions_the_screens_ask_for(root)
    impatient = _presses_wait_their_turn(root)

    # A run with lives ends somewhere whichever kind of run it was, so the
    # roguelike pair share one Records screen rather than a board each --
    # and the campaign three, whose runs do not end that way, have none.
    from .screens import screens as _screens

    roguelikes = modes_in('Roguelike')
    records_valid = bool(
        roguelikes
        and all(
            ('records', 'Records') in _screens(mode) for mode in roguelikes
        )
        and not any(
            ('records', 'Records') in _screens(mode)
            for mode in modes() if mode not in roguelikes
        )
    )

    return {
        'shell_pages_present_valid': present,
        'shell_views_keep_to_themselves_valid': not borrowing,
        'shell_views_are_named_once_valid': not misnamed,
        'shell_failure_to_open_is_reported_valid': _failure_reported_valid(),
        'shell_is_the_only_interface_valid': _only_interface_valid(),
        'shell_tokens_are_the_only_palette_valid': not stray_colours,
        'shell_tokens_are_the_only_scale_valid': not stray_sizes,
        'shell_hidden_means_hidden_valid': hidden_valid,
        'shell_both_themes_complete_valid': bool(themed and themed <= light),
        'shell_no_markup_parsing_valid': markup_free,
        'shell_components_are_pure_valid': bool(components and components_pure),
        'shell_every_screen_a_mode_names_exists_valid': screens_valid,
        'shell_every_mode_is_drawn_valid': every_mode_drawn_valid,
        'shell_every_action_asked_for_exists_valid': not unanswered,
        'shell_presses_wait_their_turn_valid': not impatient,
        'shell_every_mode_is_one_kind_of_game_valid': families_valid,
        'shell_roguelikes_share_records_valid': records_valid,
        'shell_contract_valid': bool(
            records_valid
            and
            present
            and _failure_reported_valid()
            and _only_interface_valid()
            and not stray_colours
            and not stray_sizes
            and hidden_valid
            and markup_free
            and components_pure
            and screens_valid
            and every_mode_drawn_valid
            and not borrowing
            and not misnamed
            and not unanswered
            and not impatient
            and families_valid
        ),
    }
