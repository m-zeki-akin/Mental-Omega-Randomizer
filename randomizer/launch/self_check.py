"""Regression checks for the process boundary, also runnable inside the EXE."""

import io
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from randomizer.application import launch_controller as launch


FLAGS = ['-SPAWN', '-CD', '-SPEEDCONTROL', '-LOG']


class LaunchCommandTests(unittest.TestCase):
    def controller(self):
        controller = launch.LaunchController()
        controller.state = None
        for name in (
            'append_log', 'after', 'poll_hook_log', 'cleanup_generated_root_maps',
            'disable_generated_rules_for_client', 'finish_progression_launch_context',
        ):
            setattr(controller, name, Mock())
        controller.archipelago_run_active = lambda: False
        return controller

    def start(self, controller):
        controller.start_mission_process(
            {'code': 'TEST', 'scenario': 'TEST.MAP'}, None, 1, 3,
        )

    def test_windows_process_receives_required_quotes(self):
        for root in (r'C:\Games\MO', r'C:\Games\Mental Omega', r'C:\遊戲\MO & Mods'):
            for host in ('gamemd.exe', root + r'\gamemd.exe'):
                with self.subTest(root=root, host=host):
                    controller = self.controller()
                    argv = [root + r'\Syringe.exe', host, *FLAGS]
                    controller.build_command = lambda: argv
                    expected = (
                        subprocess.list2cmdline(argv[:1])
                        + ' "' + host + '" ' + ' '.join(FLAGS)
                    )
                    with (
                        patch.object(launch.sys, 'platform', 'win32'),
                        patch.object(launch, 'GAME_ROOT', root),
                        patch.object(launch.subprocess, 'Popen') as popen,
                        patch.object(launch, 'log_event') as event,
                    ):
                        self.start(controller)
                    popen.assert_called_once_with(
                        expected, cwd=root, executable=argv[0],
                    )
                    self.assertIs(controller.active_game_process, popen.return_value)
                    self.assertEqual(event.call_args.kwargs['command'], expected)
                    controller.after.assert_called_once()
                    controller.cleanup_generated_root_maps.assert_not_called()

    def test_windows_build_command_uses_game_executable(self):
        root = PureWindowsPath(r'C:\Games\MO')
        with (
            patch.object(launch.sys, 'platform', 'win32'),
            patch.object(launch, 'GAME_LAUNCHER_EXE', root / 'Syringe.exe'),
            patch.object(launch, 'GAME_EXE', root / 'gamemd.exe'),
        ):
            self.assertEqual(
                self.controller().build_command(),
                [str(root / 'Syringe.exe'), 'gamemd.exe', *FLAGS],
            )

    def test_linux_keeps_argv_environment_and_process_group(self):
        for overrides, expected in (
            ('', 'ddraw=n,b'),
            ('d3d9=n', 'd3d9=n;ddraw=n,b'),
            ('ddraw=b', 'ddraw=b'),
        ):
            with self.subTest(overrides=overrides):
                controller = self.controller()
                argv = ['/usr/bin/wine', '/games/Mental Omega/Syringe.exe',
                        r'Z:\games\Mental Omega\gamemd.exe', *FLAGS]
                controller.build_command = lambda: argv
                with (
                    patch.object(launch.sys, 'platform', 'linux'),
                    patch.dict(os.environ, {'WINEDLLOVERRIDES': overrides}),
                    patch.object(launch.subprocess, 'Popen') as popen,
                    patch.object(launch, 'log_event'),
                ):
                    self.start(controller)
                self.assertIs(popen.call_args.args[0], argv)
                options = popen.call_args.kwargs
                self.assertEqual(options['env']['WINEDLLOVERRIDES'], expected)
                self.assertTrue(options['start_new_session'])
                self.assertNotIn('executable', options)
                self.assertNotIn('shell', options)

    def test_linux_resolves_host_with_winepath(self):
        with (
            patch.object(launch.sys, 'platform', 'linux'),
            patch.object(launch.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name),
            patch.object(launch.subprocess, 'run') as run,
        ):
            run.return_value.stdout = 'Z:\\games\\Mental Omega\\gamemd.exe\n'
            argv = self.controller().build_command()
        self.assertEqual(argv, [
            '/usr/bin/wine', str(launch.GAME_LAUNCHER_EXE),
            r'Z:\games\Mental Omega\gamemd.exe', *FLAGS,
        ])
        self.assertEqual(run.call_args.args[0], [
            '/usr/bin/winepath', '-w', str(launch.GAME_EXE),
        ])
        self.assertTrue(run.call_args.kwargs['check'])

    def test_command_preparation_failure_cleans_up(self):
        controller = self.controller()
        controller.build_command = Mock(side_effect=FileNotFoundError('Wine is missing'))
        with (
            patch.object(launch.subprocess, 'Popen') as popen,
            patch.object(launch, 'log_event'),
            patch.object(launch.messagebox, 'showerror') as error,
        ):
            self.start(controller)
        popen.assert_not_called()
        controller.cleanup_generated_root_maps.assert_called_once()
        controller.disable_generated_rules_for_client.assert_called_once()
        controller.finish_progression_launch_context.assert_called_once()
        error.assert_called_once()

    def test_quote_windows_argument(self):
        for argument, expected in (
            ('', '""'),
            ('gamemd.exe', '"gamemd.exe"'),
            ('has space', '"has space"'),
            ('end\\', '"end\\\\"'),
            ('has space\\', '"has space\\\\"'),
            ('say"hi', '"say\\"hi"'),
        ):
            with self.subTest(argument=argument):
                self.assertEqual(launch.quote_windows_argument(argument), expected)

    @unittest.skipUnless(sys.platform == 'win32', 'Requires Windows')
    def test_real_windows_process_command_line(self):
        """Read what Windows handed a real child, not what Python parsed.

        This is the only test here that leaves the process, and it used to be
        skipped whenever the build was frozen -- which is to say, in the only
        build anybody runs. It spawned a Python interpreter, and a frozen
        build has none. The packaged launcher reports its own command line
        instead, to a file: the EXE is windowed, so nothing is listening on
        stdout.
        """
        with tempfile.TemporaryDirectory(prefix='mo-cmdline-probe-') as folder:
            report = Path(folder) / 'command-line.json'
            frozen = getattr(sys, 'frozen', False)
            if frozen:
                probe = [sys.executable, f'--report-command-line={report}']
            else:
                script = (
                    'import ctypes,json,sys; from pathlib import Path; '
                    'ctypes.windll.kernel32.GetCommandLineW.restype='
                    'ctypes.c_wchar_p; '
                    'Path(sys.argv[1]).write_text(json.dumps(['
                    'ctypes.windll.kernel32.GetCommandLineW(),sys.argv[2:]]),'
                    "encoding='utf-8')"
                )
                probe = [sys.executable, '-c', script, str(report)]
            for host in (
                'gamemd.exe', r'C:\Games\MO\gamemd.exe',
                r'C:\Mental Omega\gamemd.exe',
            ):
                with self.subTest(host=host):
                    tail = launch.windows_syringe_command_line(
                        ['Syringe.exe', host, *FLAGS]
                    )
                    tail = tail.removeprefix('Syringe.exe ')
                    command = subprocess.list2cmdline(probe) + ' ' + tail
                    subprocess.run(
                        command, executable=sys.executable, check=True,
                        capture_output=True, text=True,
                    )
                    raw, argv = json.loads(
                        report.read_text(encoding='utf-8')
                    )
                    report.unlink()
                    self.assertTrue(
                        raw.endswith(' "' + host + '" ' + ' '.join(FLAGS))
                    )
                    self.assertEqual(argv, [host, *FLAGS])


def validate_launch_contract():
    """Raise on regression even in optimized, windowed PyInstaller builds."""
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LaunchCommandTests)
    result = unittest.TextTestRunner(stream=output).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError(output.getvalue())
    # Named, not counted. A bare 'skipped: 1' reads as complete coverage to
    # anyone who does not go looking for which one, and the one that used to
    # be skipped here was the only end-to-end check in the suite.
    return {
        'passed': True,
        'tests': result.testsRun,
        'skipped': [
            f'{case.id().rsplit(".", 1)[-1]}: {reason}'
            for case, reason in result.skipped
        ],
    }
