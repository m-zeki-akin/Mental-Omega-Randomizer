"""Placement helpers shared by the launcher's secondary windows."""


def center_on_pointer(root, window):
    """Place a window under the pointer that opened it.

    A Toplevel with no geometry lands wherever the window manager likes,
    which on Windows is the top-left of the primary monitor -- possibly a
    different screen from the button that was just clicked.

    Clamping is only applied when the pointer is on the primary monitor.
    Tk reports the primary screen's size, so clamping a window opened on a
    second monitor against those bounds would drag it back to the first.
    """
    window.update_idletasks()
    width = max(window.winfo_reqwidth(), window.winfo_width())
    height = max(window.winfo_reqheight(), window.winfo_height())
    pointer_x = root.winfo_pointerx()
    pointer_y = root.winfo_pointery()
    x = pointer_x - width // 2
    y = pointer_y - height // 2
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    if 0 <= pointer_x < screen_width and 0 <= pointer_y < screen_height:
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
    # Position only. Giving geometry a size as well would freeze the window at
    # whatever it measured before it was mapped and stop it fitting its own
    # contents afterwards.
    window.geometry(f'+{int(x)}+{int(y)}')
