"""Skirmish Shop Mode: choosing a line-up and starting the battle.

A campaign mission is a scenario the game already has; a skirmish is a map
copied into place beside a file describing who is in it. So this does not
ride the mission launch path: that one writes the campaign spawn file, whose
``IsSinglePlayer`` ends a skirmish before the engine finishes processing
sides, and it records a defeat for a mission code a skirmish does not have.
What it does reuse is everything after that -- the Syringe command line, the
process, the watcher that notices the game has closed.

This is the mode's skeleton: a line-up, a map, a launch. The run that
remembers what happened comes next, and it is waiting on one unknown --
victory is detected from markers in the game's hook log, keyed on mission
TeamType names that a skirmish has none of.
"""

from pathlib import Path
import random
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import (
    GAME_EXE,
    GAME_LAUNCHER_EXE,
    GAME_ROOT,
    SPAWN_INI,
)
from randomizer.skirmish.factions import skirmish_countries
from randomizer.skirmish.maps import maps_for_players, skirmish_map_pool
from randomizer.skirmish.spawn import (
    AI_HANDICAP_EASY,
    AI_HANDICAP_HARD,
    AI_HANDICAP_NORMAL,
    SkirmishHouse,
    skirmish_spawn_ini_text,
)


SKIRMISH_MODE = 'Skirmish Shop'
SPAWN_MAP_INI = GAME_ROOT / 'spawnmap.ini'
NO_ALLY = 'No ally'
# Colours are indexes into the client's own list. The player takes the first
# and every other house takes the next, so no two houses share one.
HOUSE_COLORS = (0, 2, 4, 6, 8, 10, 12, 14)
AI_HANDICAPS = {
    'Easy': AI_HANDICAP_EASY,
    'Normal': AI_HANDICAP_NORMAL,
    'Hard': AI_HANDICAP_HARD,
}
# What the preview is allowed to take up, in pixels. Previews are wider than
# they are tall and vary in size, so the image is stepped down by whole
# factors until it fits -- Tk subsamples by integers and nothing else.
PREVIEW_BOX = (420, 300)


class SkirmishController:
    def initialize_skirmish_controller(self):
        self.skirmish_country_var = tk.StringVar(value='')
        self.skirmish_ally_var = tk.StringVar(value=NO_ALLY)
        self.skirmish_enemy_count_var = tk.StringVar(
            value=str(self.config.get('skirmish_enemy_count') or 2)
        )
        self.skirmish_handicap_var = tk.StringVar(
            value=str(self.config.get('skirmish_enemy_skill') or 'Hard')
        )
        self.skirmish_search_var = tk.StringVar(value='')
        self.skirmish_map_detail_var = tk.StringVar(value='')
        self.skirmish_message_var = tk.StringVar(value='')
        self._skirmish_maps_by_id = {}
        self._skirmish_preview_image = None
        self._skirmish_launch = None

    # -- the mode ---------------------------------------------------------

    def skirmish_mode_selected(self):
        variable = getattr(self, 'progression_mode_var', None)
        return bool(variable is not None and variable.get() == SKIRMISH_MODE)

    def skirmish_launch_active(self):
        return getattr(self, '_skirmish_launch', None) is not None

    def randomizer_launch_active(self):
        if self.skirmish_launch_active():
            return True
        return super().randomizer_launch_active()

    def on_new_seed(self):
        if not self.skirmish_mode_selected():
            return super().on_new_seed()
        # There is no campaign run to seed here. The button that starts a
        # game in this mode is the one beside the map.
        self.workspace_tabs.select(self.skirmish_tab)
        self.skirmish_message_var.set(
            'Choose a map below and launch the battle.'
        )

    def on_launch_selected(self):
        if self.skirmish_mode_selected():
            self.launch_skirmish()
            return
        return super().on_launch_selected()

    def on_progression_mode_changed(self, event=None):
        # After the other modes have arranged the workspace: the mode that is
        # not selected puts the mission list back, and this takes it away
        # again when the mode that is selected has no missions.
        result = super().on_progression_mode_changed(event)
        self.sync_skirmish_workspace()
        return result

    def sync_skirmish_workspace(self):
        """Show the skirmish tab for its own mode and hide it otherwise."""
        if not all(hasattr(self, name) for name in (
            'skirmish_tab', 'workspace_tabs', 'mission_view_frame',
        )):
            return
        tabs = set(self.workspace_tabs.tabs())
        skirmish_tab = str(self.skirmish_tab)
        if self.skirmish_mode_selected():
            if str(self.mission_view_frame) in tabs:
                self.workspace_tabs.forget(self.mission_view_frame)
            if skirmish_tab not in set(self.workspace_tabs.tabs()):
                self.workspace_tabs.insert(
                    0, self.skirmish_tab, text='Skirmish'
                )
            if hasattr(self, 'seed_action_button'):
                self.seed_action_button.configure(text='Choose a Battle')
            self.refresh_skirmish_countries()
            self.refresh_skirmish_maps()
        elif skirmish_tab in tabs:
            self.workspace_tabs.forget(self.skirmish_tab)

    # -- the line-up ------------------------------------------------------

    def refresh_skirmish_countries(self):
        if not hasattr(self, 'skirmish_country_combo'):
            return
        countries = skirmish_countries()
        labels = [country.display for country in countries]
        self._skirmish_country_by_label = {
            country.display: country for country in countries
        }
        self.skirmish_country_combo.configure(values=labels)
        self.skirmish_ally_combo.configure(values=[NO_ALLY, *labels])
        saved = str(self.config.get('skirmish_country') or '')
        if self.skirmish_country_var.get() not in labels:
            self.skirmish_country_var.set(
                saved if saved in labels else (labels[0] if labels else '')
            )
        saved_ally = str(self.config.get('skirmish_ally') or NO_ALLY)
        if self.skirmish_ally_var.get() not in {NO_ALLY, *labels}:
            self.skirmish_ally_var.set(
                saved_ally if saved_ally in labels else NO_ALLY
            )

    def skirmish_country(self, variable):
        by_label = getattr(self, '_skirmish_country_by_label', {})
        return by_label.get(variable.get())

    def skirmish_required_seats(self):
        """How many houses the map has to place, the player included."""
        allies = 0 if self.skirmish_ally_var.get() == NO_ALLY else 1
        try:
            enemies = int(self.skirmish_enemy_count_var.get())
        except ValueError:
            enemies = 1
        return 1 + allies + max(1, enemies)

    # -- the map ----------------------------------------------------------

    def refresh_skirmish_maps(self, *_args):
        if not hasattr(self, 'skirmish_map_tree'):
            return
        seats = self.skirmish_required_seats()
        search = self.skirmish_search_var.get().strip().lower()
        pool = maps_for_players(skirmish_map_pool(), seats)
        if search:
            pool = tuple(
                entry for entry in pool
                if search in entry.name.lower()
                or search in entry.path.stem.lower()
            )
        selected = self.selected_skirmish_map()
        tree = self.skirmish_map_tree
        tree.delete(*tree.get_children())
        self._skirmish_maps_by_id = {}
        for entry in sorted(pool, key=lambda item: item.name.lower()):
            item_id = str(entry.path)
            self._skirmish_maps_by_id[item_id] = entry
            tree.insert('', 'end', iid=item_id, values=(
                entry.name,
                entry.seats,
                ', '.join(entry.game_modes),
            ))
        if selected is not None and str(selected.path) in (
            self._skirmish_maps_by_id
        ):
            tree.selection_set(str(selected.path))
        self.skirmish_message_var.set(
            f'{len(self._skirmish_maps_by_id)} maps seat {seats}.'
            if self._skirmish_maps_by_id
            else f'No installed map seats {seats}.'
        )
        self.on_skirmish_map_selected()

    def selected_skirmish_map(self):
        tree = getattr(self, 'skirmish_map_tree', None)
        if tree is None:
            return None
        selection = tree.selection()
        if not selection:
            return None
        return self._skirmish_maps_by_id.get(selection[0])

    def on_skirmish_map_selected(self, _event=None):
        entry = self.selected_skirmish_map()
        self.skirmish_launch_button.configure(
            state='normal'
            if entry is not None and not self.randomizer_launch_active()
            else 'disabled'
        )
        if entry is None:
            self.skirmish_map_detail_var.set('')
            self.skirmish_preview_label.configure(image='')
            self._skirmish_preview_image = None
            return
        self.skirmish_map_detail_var.set(
            f'{entry.name}\n{entry.seats} seats '
            f'({entry.players} claimed, {entry.starts} starting points)\n'
            f'{entry.path.name}'
        )
        self._show_skirmish_preview(entry.preview)

    def _show_skirmish_preview(self, path):
        if not path or not Path(path).is_file():
            self.skirmish_preview_label.configure(image='', text='No preview')
            self._skirmish_preview_image = None
            return
        try:
            image = tk.PhotoImage(master=self, file=str(path))
        except tk.TclError:
            self.skirmish_preview_label.configure(
                image='', text='Preview could not be read'
            )
            self._skirmish_preview_image = None
            return
        width_box, height_box = PREVIEW_BOX
        factor = 1
        while (
            image.width() // factor > width_box
            or image.height() // factor > height_box
        ) and factor < 8:
            factor += 1
        if factor > 1:
            image = image.subsample(factor)
        # Held on the controller: Tk drops an image the moment nothing in
        # Python refers to it, and the label then shows nothing.
        self._skirmish_preview_image = image
        self.skirmish_preview_label.configure(image=image, text='')

    # -- the battle -------------------------------------------------------

    def skirmish_houses(self):
        """Return the computer players, ally first, in seating order."""
        handicap = AI_HANDICAPS.get(self.skirmish_handicap_var.get(),
                                    AI_HANDICAP_HARD)
        countries = skirmish_countries()
        houses = []
        ally = self.skirmish_country(self.skirmish_ally_var)
        if ally is not None:
            houses.append(SkirmishHouse(
                country=ally.index,
                color=HOUSE_COLORS[len(houses) + 1],
                friendly=True,
                handicap=handicap,
            ))
        enemies = self.skirmish_required_seats() - len(houses) - 1
        for _index in range(enemies):
            # The opposition is drawn rather than chosen: which armies turn
            # up is the run's business, not a setting.
            country = random.choice(countries)
            houses.append(SkirmishHouse(
                country=country.index,
                color=HOUSE_COLORS[len(houses) + 1],
                friendly=False,
                handicap=handicap,
            ))
        return tuple(houses)

    def launch_skirmish(self):
        if self.randomizer_launch_active():
            self.skirmish_message_var.set(
                'Wait for the running game to close.'
            )
            return
        entry = self.selected_skirmish_map()
        if entry is None:
            self.skirmish_message_var.set('Choose a map first.')
            return
        player = self.skirmish_country(self.skirmish_country_var)
        if player is None:
            self.skirmish_message_var.set('Choose the country you play.')
            return
        missing = [
            path for path in (GAME_LAUNCHER_EXE, GAME_EXE)
            if not path.exists()
        ]
        if missing:
            messagebox.showerror(
                'Cannot Launch Skirmish',
                'Missing launch executable(s): '
                + ', '.join(str(path) for path in missing),
                parent=self,
            )
            return
        houses = self.skirmish_houses()
        seed = random.randrange(1, 2 ** 31)
        battle = {
            'map': entry,
            'player': player,
            'houses': houses,
            'seed': seed,
        }
        self.config['skirmish_country'] = player.display
        self.config['skirmish_ally'] = self.skirmish_ally_var.get()
        self.config['skirmish_enemy_count'] = self.skirmish_enemy_count_var.get()
        self.config['skirmish_enemy_skill'] = self.skirmish_handicap_var.get()
        self.save_current_launcher_config()
        self.run_in_background(
            'Starting skirmish, please wait…',
            'Copying the map and writing the battle setup.',
            lambda: self.prepare_skirmish_launch_files(battle),
            lambda _result: self.start_skirmish_process(battle),
            lambda exc, detail: self.handle_skirmish_launch_error(exc, detail),
        )

    def prepare_skirmish_launch_files(self, battle):
        """Put the map and the battle setup where the spawner reads them."""
        # A generated rulesmo.ini left enabled would be loaded by this match
        # as well, so the campaign path's cleanup runs here too.
        self.disable_generated_rules_for_client()
        self.cleanup_generated_root_maps()
        entry = battle['map']
        shutil.copy2(entry.path, SPAWN_MAP_INI)
        SPAWN_INI.write_text(
            skirmish_spawn_ini_text(
                map_name=entry.name,
                player_country=battle['player'].index,
                player_color=HOUSE_COLORS[0],
                houses=battle['houses'],
                seed=battle['seed'],
            ),
            encoding='utf-8',
        )
        self.write_launch_options(
            self.get_selected_difficulty_value(),
            self.get_selected_game_speed_value(),
        )
        return True

    def handle_skirmish_launch_error(self, exc, detail):
        self._skirmish_launch = None
        self.append_log(detail, error=True)
        log_event(
            'skirmish_launch_failed',
            error_type=exc.__class__.__name__,
            error=str(exc),
        )
        messagebox.showerror(
            'Launch Failed',
            'Failed to write the skirmish files. See log for details.',
            parent=self,
        )
        self.on_skirmish_map_selected()

    def start_skirmish_process(self, battle):
        from .launch_controller import windows_syringe_command_line

        command = self.build_command()
        popen_options = {}
        launch_target = command
        if sys.platform == 'win32':
            # Syringe parses its own raw command line and refuses to start
            # unless the host executable is quoted.
            launch_target = windows_syringe_command_line(command)
            popen_options['executable'] = command[0]
            command_text = launch_target
        else:
            command_text = subprocess.list2cmdline(command)
        try:
            process = subprocess.Popen(
                launch_target, cwd=str(GAME_ROOT), **popen_options
            )
        except OSError as exc:
            self.handle_skirmish_launch_error(exc, str(exc))
            return
        self._skirmish_launch = battle
        self.active_game_process = process
        # No hook: a skirmish has no mission markers to watch for. The
        # watcher still runs, because noticing the game has closed is what
        # ends the launch.
        self.active_hook = None
        self.active_mission_attempt = None
        entry = battle['map']
        self.append_log(
            f'Launched skirmish on {entry.name} '
            f'({len(battle["houses"])} computer players) PID={process.pid}.'
        )
        log_event(
            'skirmish_process_started',
            pid=process.pid,
            map=entry.path.name,
            seats=entry.seats,
            player_country=battle['player'].country_id,
            houses=[house.country for house in battle['houses']],
            seed=battle['seed'],
        )
        self.skirmish_message_var.set(f'Playing {entry.name}.')
        self.on_skirmish_map_selected()
        self.poll_hook_log()

    def finish_progression_launch_context(self):
        if self.skirmish_launch_active():
            self._skirmish_launch = None
            if hasattr(self, 'skirmish_map_tree'):
                self.skirmish_message_var.set('Battle closed.')
                self.on_skirmish_map_selected()
            return
        return super().finish_progression_launch_context()
