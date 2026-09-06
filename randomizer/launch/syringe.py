"""Handing a command line to Syringe, which parses its own.

Syringe reads the raw command line rather than the argument vector, and
refuses to start unless the host executable is quoted. Python's own quoting
drops those quotes whenever the path has no whitespace, so the quoting is
done here, at the last boundary before the string is handed over.
"""

import subprocess


def quote_windows_argument(argument):
    """Quote even whitespace-free arguments, preserving Windows CRT escaping."""
    encoded = subprocess.list2cmdline([argument])
    if encoded.startswith('"'):
        return encoded
    # list2cmdline already escapes embedded quotes. When adding outer quotes,
    # trailing backslashes must be doubled so they cannot escape the closing one.
    trailing_backslashes = len(argument) - len(argument.rstrip('\\'))
    return '"' + encoded + '\\' * trailing_backslashes + '"'


def windows_syringe_command_line(argv):
    """Syringe parses its raw command line and requires a quoted host EXE.

    Passing a list to Windows Popen loses these mandatory quotes whenever the
    host path has no whitespace. Keep argv structured until this final boundary.
    """
    return ' '.join((
        subprocess.list2cmdline(argv[:1]),
        quote_windows_argument(argv[1]),
        subprocess.list2cmdline(argv[2:]),
    )).rstrip()
