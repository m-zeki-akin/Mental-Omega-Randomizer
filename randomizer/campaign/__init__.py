"""What a campaign run is, apart from the window looking at it.

The three campaign modes are one run in three orders, and everything
about that run is already written down in one file. What was missing was
somewhere to ask about it that does not need a window: the rules for
which mission is open and how far each one got lived on the classic
window's controllers, where only a Tk instance could reach them.

They live here now, as functions over the state a run is stored as, and
the classic window calls them too. One rule, two readers.
"""
