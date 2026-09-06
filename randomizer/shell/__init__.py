"""The window the interface is drawn in.

This is the only module in the launcher that knows a browser engine exists.
It opens a WebView2 window on the pages under ``web/``, hands them one
object to call, and gets out of the way -- so that everything the interface
does still goes through ``randomizer.api`` and nothing under it learns what
is drawing it.
"""

from .host import ShellError, run_shell, web_root


__all__ = ['ShellError', 'run_shell', 'web_root']
