"""Wheel scrolling that stops at the innermost scrollable widget.

Tk delivers wheel events to the widget under the pointer, and several classes
(Treeview, Notebook, Combobox, Scrollbar) act on them by default. Together with
the window-wide ``bind_all`` fallbacks that scroll the Shop and Settings
canvases, one notch used to move a nested tree *and* the page beneath it, or
cycle a notebook tab. Widgets registered here claim the wheel: the innermost
registered ancestor of whatever sits under the pointer is the only thing that
moves, and the event is swallowed before any class binding sees it.
"""

import tkinter as tk

WHEEL_EVENTS = (
    '<MouseWheel>',
    '<Shift-MouseWheel>',
    '<Alt-MouseWheel>',
    '<Shift-Alt-MouseWheel>',
)

_OWNER = '_mo_scroll_owner'
_SHIFT = 0x0001


def scroll_owner(widget, *, target=None, units=1):
    """Make widget the wheel target for its subtree, scrolling target."""
    setattr(widget, _OWNER, (widget if target is None else target, units))
    return widget


def claim_wheel(widget):
    """Swallow wheel events on widget so no class binding also reacts."""
    for sequence in WHEEL_EVENTS:
        widget.bind(sequence, _claim, add='+')
    return widget


def block_wheel(widget, sequence):
    """Drop one wheel sequence that cannot be routed to a scroll owner.

    Sequences such as <TouchpadScroll> only exist in Tcl/Tk 9. Binding an
    unknown sequence raises, so a launcher built against the pinned Tcl/Tk 8.6
    runtime would fail while building its widgets. Skip what the runtime does
    not know instead.
    """
    try:
        widget.bind(sequence, lambda _event: 'break', add='+')
    except tk.TclError:
        return widget
    return widget


def scroll_under_pointer(widget, event):
    """Scroll the innermost owner under the pointer; None when there is none."""
    axis = 'x' if event.state & _SHIFT else 'y'
    target, units = _owner_under_pointer(widget, event, axis)
    if target is None:
        return None
    steps = -units if event.delta > 0 else units
    if axis == 'x':
        target.xview_scroll(steps, 'units')
    else:
        target.yview_scroll(steps, 'units')
    return 'break'


def _claim(event):
    scroll_under_pointer(event.widget, event)
    return 'break'


def _owner_under_pointer(widget, event, axis):
    try:
        found = widget.winfo_containing(event.x_root, event.y_root)
    except (KeyError, tk.TclError):
        return None, 0
    while found is not None:
        registration = getattr(found, _OWNER, None)
        if registration is not None and _can_scroll(registration[0], axis):
            return registration
        found = getattr(found, 'master', None)
    return None, 0


def _can_scroll(target, axis):
    try:
        first, last = target.xview() if axis == 'x' else target.yview()
    except (AttributeError, ValueError, tk.TclError):
        return False
    return first > 0.0 or last < 1.0
