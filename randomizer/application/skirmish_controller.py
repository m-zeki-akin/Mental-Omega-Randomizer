"""Skirmish Shop Mode: the run, its battles, and starting one.

A campaign mission is a scenario the game already has; a skirmish is a map
copied into place beside a file describing who is in it. So this does not
ride the mission launch path: that one writes the campaign spawn file, whose
``IsSinglePlayer`` ends a skirmish before the engine finishes processing
sides, and it records a defeat for a mission code a skirmish does not have.
What it does reuse is everything after that -- the Syringe command line, the
process, the watcher that notices the game has closed.

A run picks its army once and is then offered battles: three to choose from,
or one challenge every fifth. Winning moves it on, losing costs a life and
leaves the battle standing. Runs are stored side by side and never touch
each other.
"""

from datetime import date
from pathlib import Path
import subprocess
import sys
import tkinter as tk
import uuid
from tkinter import messagebox

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import (
    DEBUG_LOG,
    GAME_EXE,
    GAME_LAUNCHER_EXE,
    GAME_ROOT,
)
from randomizer.shop.model import RunStatus
from randomizer.skirmish.factions import country_by_index, skirmish_countries
from randomizer.skirmish.launch import (
    PLAYER_NAME as SKIRMISH_PLAYER_NAME,
    build_battle,
    houses_for,
    prepare_battle,
)
from randomizer.skirmish.maps import map_by_relative_path
from randomizer.skirmish.persistence import (
    SkirmishPersistenceError,
    SkirmishRepository,
)
from randomizer.skirmish.leaderboard import (
    board_row,
    load_board,
    reached_text,
    record_finished_run,
)
from randomizer.skirmish.progression import describe_offer
from randomizer.skirmish.table import deal, enemy_pool
from randomizer.skirmish.ai import remove_staged_ai_file
from randomizer.skirmish.shop import (
    owned_stacks,
    purchase_labels,
    shelf_for,
)
from randomizer.skirmish.results import (
    last_game_result,
    read_debug_log_tail,
)
from randomizer.skirmish.stats import stats_lines
from randomizer.skirmish.transitions import (
    SkirmishTransitionError,
    buy_upgrade,
    commit_offer,
    give_up,
    record_defeat,
    record_victory,
    run_progress_text,
    skip_warmup,
    start_run,
)


SKIRMISH_MODE = 'Skirmish Shop'
# The player's house is named in the spawn file and named again in the score
# block the game writes at the end, which is how the launcher finds its own
# result among the houses.
SKIRMISH_PLAYER_NAME = 'Commander'
# Colours are indexes into the client's own list. The player takes the first
# and every other house takes the next, so no two houses share one.
HOUSE_COLORS = (0, 2, 4, 6, 8, 10, 12, 14)
# What a card's preview is allowed to take up, in pixels. Tk subsamples by
# whole factors and nothing else, so the image steps down until it fits.
PREVIEW_BOX = (300, 210)


class SkirmishController:
    def initialize_skirmish_controller(self):
        self.skirmish_repository = SkirmishRepository()
        self.skirmish_run = None
        self.skirmish_country_var = tk.StringVar(value='')
        self.skirmish_ally_var = tk.StringVar(value='')
        self.skirmish_progress_var = tk.StringVar(value='No run')
        self.skirmish_army_var = tk.StringVar(value='')
        self.skirmish_message_var = tk.StringVar(value='')
        self.skirmish_ore_var = tk.StringVar(value='Ore: 0')
        self.skirmish_shop_help_var = tk.StringVar(value='')
        self.skirmish_owned_var = tk.StringVar(value='')
        self.skirmish_board_detail_var = tk.StringVar(value='')
        self._skirmish_board = ()
        self._skirmish_shelf = ()
        self._skirmish_country_by_label = {}
        self._skirmish_preview_images = {}
        self._skirmish_launch = None
        self._skirmish_setup_open = False

    # -- the mode ---------------------------------------------------------

    def skirmish_mode_selected(self):
        variable = getattr(self, 'progression_mode_var', None)
        return bool(variable is not None and variable.get() == SKIRMISH_MODE)

    def skirmish_launch_active(self):
        return getattr(self, '_skirmish_launch', None) is not None

    def skirmish_launch_blocked(self):
        """Whether something is already playing.

        Deliberately not ``randomizer_launch_active``: that one is true
        whenever a randomizer run exists, which is most of the time and has
        nothing to do with whether a game is open.
        """
        return bool(
            self.game_process_running()
            or self.skirmish_launch_active()
            or getattr(self, 'shop_launch_active', lambda: False)()
        )

    def on_new_seed(self):
        if not self.skirmish_mode_selected():
            return super().on_new_seed()
        # There is no campaign run to seed here. What starts a game in this
        # mode is a battle card, and what starts a run is the setup panel.
        self.workspace_tabs.select(self.skirmish_tab)
        if self.skirmish_run is None or (
            self.skirmish_run.status is not RunStatus.ACTIVE
        ):
            self.open_skirmish_setup()
        else:
            self.skirmish_message_var.set('Choose a battle below.')

    def on_launch_selected(self):
        if not self.skirmish_mode_selected():
            return super().on_launch_selected()
        # The main Launch button has no card under it, so it only acts when
        # there is one battle it could mean: the one already committed to,
        # or a challenge, which is offered alone.
        run = self.skirmish_run
        if run is None or run.status is not RunStatus.ACTIVE:
            self.skirmish_message_var.set('Start a run first.')
            return
        if run.committed_offer is not None:
            self.launch_skirmish_offer(run.committed_offer)
        elif len(run.offers) == 1:
            self.launch_skirmish_offer(0)
        else:
            self.workspace_tabs.select(self.skirmish_tab)
            self.skirmish_message_var.set('Choose a battle card.')

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
                self.seed_action_button.configure(text='Skirmish Run')
            self.refresh_skirmish_mode()
        elif skirmish_tab in tabs:
            self.workspace_tabs.forget(self.skirmish_tab)

    # -- the army ---------------------------------------------------------

    def refresh_skirmish_countries(self):
        if not hasattr(self, 'skirmish_country_combo'):
            return
        countries = skirmish_countries()
        labels = [country.display for country in countries]
        self._skirmish_country_by_label = {
            country.display: country for country in countries
        }
        self.skirmish_country_combo.configure(values=labels)
        self.skirmish_ally_combo.configure(values=labels)
        for variable, key, fallback in (
            (self.skirmish_country_var, 'skirmish_country', 0),
            (self.skirmish_ally_var, 'skirmish_ally', 3),
        ):
            if variable.get() in labels:
                continue
            saved = str(self.config.get(key) or '')
            variable.set(
                saved if saved in labels
                else (labels[fallback] if len(labels) > fallback else '')
            )

    def skirmish_country(self, variable):
        return self._skirmish_country_by_label.get(variable.get())

    def skirmish_enemy_text(self, offer):
        """Name the armies this battle is fought against."""
        names = []
        for index in offer.enemy_countries:
            country = country_by_index(index)
            names.append(
                f'{country.side} {country.label}' if country else str(index)
            )
        return ', '.join(names)

    def skirmish_army_text(self, run):
        player = country_by_index(run.player_country)
        ally = country_by_index(run.ally_country)
        return (
            f'{player.display if player else run.player_country}'
            f'   ally: {ally.display if ally else run.ally_country}'
        )

    # -- the run ----------------------------------------------------------

    def open_skirmish_setup(self):
        """Show the panel that starts a new run."""
        self._skirmish_setup_open = True
        self.refresh_skirmish_countries()
        self.refresh_skirmish_mode()

    def start_skirmish_run(self):
        if self.skirmish_launch_blocked():
            self.skirmish_message_var.set('Wait for the running game to close.')
            return
        player = self.skirmish_country(self.skirmish_country_var)
        ally = self.skirmish_country(self.skirmish_ally_var)
        if player is None or ally is None:
            self.skirmish_message_var.set('Choose an army and an ally.')
            return
        try:
            run = start_run(
                run_id=uuid.uuid4().hex,
                seed=uuid.uuid4().hex[:12].upper(),
                player_country=player.index,
                ally_country=ally.index,
                created=date.today().isoformat(),
                # So the ally is not empty-handed in the opening battle: it
                # shops out of what a victory pays, and at the start nothing
                # has been won.
                ally_roster=ally.country_id,
            )
            run = self.offer_skirmish_battles(run)
        except SkirmishTransitionError as exc:
            self.skirmish_message_var.set(str(exc))
            return
        self.config['skirmish_country'] = player.display
        self.config['skirmish_ally'] = ally.display
        self.save_current_launcher_config()
        self.skirmish_run = self.skirmish_repository.save_run(run)
        self._skirmish_setup_open = False
        log_event(
            'skirmish_run_started',
            run_id=run.run_id,
            seed=run.seed,
            player_country=player.country_id,
            ally_country=ally.country_id,
        )
        self.skirmish_message_var.set(
            f'Run started as {player.display}, allied with {ally.display}.'
        )
        self.refresh_skirmish_mode()

    def skirmish_enemy_pool(self, run):
        """Return the countries a battle may be fought against."""
        return enemy_pool(run)

    def offer_skirmish_battles(self, run):
        """Put this battle's offers on the table, drawing them if needed."""
        return deal(run)

    def skip_skirmish_warmup(self):
        """Step past the warmup without fighting it."""
        run = self.skirmish_run
        if run is None or not run.warmup:
            return
        if self.skirmish_launch_blocked():
            self.skirmish_message_var.set('Wait for the running game to close.')
            return
        try:
            run = self.offer_skirmish_battles(skip_warmup(run))
        except SkirmishTransitionError as exc:
            self.skirmish_message_var.set(str(exc))
            return
        self.skirmish_run = self.skirmish_repository.save_run(run)
        log_event('skirmish_warmup_skipped', run_id=run.run_id)
        self.skirmish_message_var.set(
            'Warmup skipped. The run starts at battle 1.'
        )
        self.refresh_skirmish_mode()

    def refresh_skirmish_board(self):
        """Repaint the board of finished runs."""
        tree = getattr(self, 'skirmish_board_tree', None)
        if tree is None or not tree.winfo_exists():
            return
        self._skirmish_board = load_board()
        tree.delete(*tree.get_children())
        for index, entry in enumerate(self._skirmish_board):
            tree.insert('', 'end', iid=str(index), values=board_row(entry))
        self.skirmish_board_detail_var.set(
            'No run has ended yet.' if not self._skirmish_board
            else 'Select a run to see what it did.'
        )

    def refresh_skirmish_board_detail(self, _event=None):
        tree = getattr(self, 'skirmish_board_tree', None)
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            return
        index = int(selection[0])
        if index >= len(self._skirmish_board):
            return
        entry = self._skirmish_board[index]
        self.skirmish_board_detail_var.set(
            f'{reached_text(entry)}   seed {entry.seed}\n'
            + '   '.join(stats_lines(entry.stats))
        )

    def record_skirmish_run_end(self, run, outcome):
        """Put a finished run on the board, which is where it goes on living.

        A run that ends is deleted or left in the list as a dead row, and
        either way what it did would be gone.
        """
        try:
            record_finished_run(run, outcome)
        except OSError as exc:
            self.append_log(f'Could not write the skirmish board: {exc}', error=True)
            return
        log_event(
            'skirmish_run_recorded',
            run_id=run.run_id,
            outcome=outcome,
            tier=run.tier,
            nightmare=run.nightmare,
            **run.stats.to_dict(),
        )

    def give_up_skirmish_run(self):
        run = self.skirmish_run
        if run is None or run.status is not RunStatus.ACTIVE:
            return
        if self.skirmish_launch_blocked():
            self.skirmish_message_var.set('Wait for the running game to close.')
            return
        if not messagebox.askyesno(
            'Give Up Skirmish Run?',
            f'End this run at battle {run.battle}?\n\n'
            'The run is kept in the list, but it cannot be played on.',
            parent=self,
        ):
            return
        ended = give_up(run)
        self.skirmish_run = self.skirmish_repository.save_run(ended)
        self.record_skirmish_run_end(ended, 'Gave up')
        self.refresh_skirmish_board()
        self.skirmish_message_var.set(
            f'Gave up at battle {run.battle}. Start a new run when ready.'
        )
        self.refresh_skirmish_mode()

    # -- painting ---------------------------------------------------------

    def refresh_skirmish_mode(self, *_args):
        if not hasattr(self, 'skirmish_battle_cards'):
            return
        try:
            self.skirmish_run = self.skirmish_repository.load_run()
        except SkirmishPersistenceError as exc:
            self.skirmish_message_var.set(str(exc))
            self.skirmish_run = None
        run = self.skirmish_run
        playable = bool(run is not None and run.status is RunStatus.ACTIVE)
        if self._skirmish_setup_open or not playable:
            self.skirmish_setup_frame.grid(row=0, column=0, sticky='ew')
            self.refresh_skirmish_countries()
        else:
            self.skirmish_setup_frame.grid_remove()
        if run is None:
            self.skirmish_progress_var.set('No run')
            self.skirmish_army_var.set('')
            self.skirmish_header_frame.grid_remove()
            self.skirmish_cards_frame.grid_remove()
            self.refresh_skirmish_run_window()
            return
        self.skirmish_header_frame.grid(
            row=1, column=0, sticky='ew', pady=(8, 0)
        )
        status = (
            '' if run.status is RunStatus.ACTIVE
            else f' — {run.status.value}'
        )
        self.skirmish_progress_var.set(run_progress_text(run) + status)
        self.skirmish_army_var.set(self.skirmish_army_text(run))
        self.skirmish_give_up_button.configure(
            state='normal' if playable else 'disabled'
        )
        # The skip is the warmup's own, so it is there while the warmup is.
        if playable and run.warmup:
            self.skirmish_skip_button.grid()
            self.skirmish_skip_button.configure(
                state='disabled' if self.skirmish_launch_blocked() else 'normal'
            )
        else:
            self.skirmish_skip_button.grid_remove()
        if playable:
            self.skirmish_cards_frame.grid(
                row=2, column=0, sticky='nsew', pady=(8, 0)
            )
            self.skirmish_shop_frame.grid(
                row=3, column=0, sticky='nsew', pady=(8, 0)
            )
            self.refresh_skirmish_cards(run)
            if run.warmup:
                # The warmup is fought with what you have. There is nothing
                # to spend and nothing riding on it.
                self.skirmish_shop_frame.grid_remove()
                self.skirmish_ore_var.set(f'Ore: {run.coins}')
            else:
                self.refresh_skirmish_shop(run)
        else:
            self.skirmish_cards_frame.grid_remove()
            self.skirmish_shop_frame.grid_remove()
            self.skirmish_ore_var.set(f'Ore: {run.coins}')
        self.refresh_skirmish_run_window()

    def refresh_skirmish_cards(self, run):
        blocked = self.skirmish_launch_blocked()
        for index, card in enumerate(self.skirmish_battle_cards):
            offer = run.offers[index] if index < len(run.offers) else None
            if offer is None:
                card['frame'].grid_remove()
                continue
            card['frame'].grid()
            entry = map_by_relative_path(offer.map_path)
            card['frame'].configure(
                text='Challenge' if offer.challenge else f'Battle {index + 1}'
            )
            card['name'].set(offer.map_name or offer.map_path)
            missing = entry is None
            enemies = self.skirmish_enemy_text(offer)
            card['detail'].set(
                'This map is not installed any more.' if missing
                else f'{describe_offer(offer)}\n{enemies}'
            )
            card['tooltip'].text = (
                f'{offer.map_name}\n{describe_offer(offer)}\n'
                f'against {enemies}\n{offer.seats} seats'
            )
            self._show_skirmish_preview(
                card, entry.preview if entry is not None else None
            )
            committed = run.committed_offer
            card['launch_button'].configure(
                text=(
                    'Fight This Challenge' if offer.challenge
                    else 'Fight This Battle'
                ),
                state=(
                    'disabled'
                    if missing or blocked
                    or (committed is not None and committed != index)
                    else 'normal'
                ),
            )

    def _show_skirmish_preview(self, card, path):
        label = card['preview_label']
        if not path or not Path(path).is_file():
            label.configure(image='', text='No preview')
            self._skirmish_preview_images.pop(id(card), None)
            return
        try:
            image = tk.PhotoImage(master=self, file=str(path))
        except tk.TclError:
            label.configure(image='', text='Preview could not be read')
            self._skirmish_preview_images.pop(id(card), None)
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
        # Held here: Tk drops an image the moment nothing in Python refers to
        # it, and the label then shows nothing.
        self._skirmish_preview_images[id(card)] = image
        label.configure(image=image, text='')

    # -- the shop ---------------------------------------------------------

    def skirmish_side(self, run):
        country = country_by_index(run.player_country)
        return country.side if country else ''

    def skirmish_country_id(self, run):
        """The country the shelf is drawn for: an army, not a side."""
        country = country_by_index(run.player_country)
        return country.country_id if country else ''

    def refresh_skirmish_shop(self, run):
        """Paint this battle's six offers, and what has been done with them."""
        if not hasattr(self, 'skirmish_upgrade_cards'):
            return
        self.skirmish_ore_var.set(f'Ore: {run.coins}')
        side = self.skirmish_side(run)
        self._skirmish_shelf = shelf_for(run, self.skirmish_country_id(run))
        blocked = self.skirmish_launch_blocked()
        playable = run.status is RunStatus.ACTIVE
        for index, card in enumerate(self.skirmish_upgrade_cards):
            upgrade = (
                self._skirmish_shelf[index]
                if index < len(self._skirmish_shelf) else None
            )
            if upgrade is None:
                card['frame'].grid_remove()
                continue
            card['frame'].grid()
            owned = owned_stacks(
                run.purchases, upgrade.unit, upgrade.buff_type
            )
            card['name'].set(
                f'{"OWNED  " if owned else ""}{upgrade.name}'
            )
            card['effect'].set(upgrade.effect)
            # A bought card keeps its place and says so. The six stand for
            # the whole battle, so buying one is something the player can
            # see happen rather than a list rearranging itself.
            card['price'].set(
                'Bought' if owned else f'{upgrade.price} Ore'
            )
            card['tooltip'].text = (
                f'{upgrade.name}\n{upgrade.effect}\n{upgrade.description}'
                if upgrade.description
                else f'{upgrade.name}\n{upgrade.effect}'
            )
            affordable = run.coins >= upgrade.price
            card['button'].configure(
                text='Bought' if owned else 'Buy',
                state=(
                    'disabled'
                    if owned or blocked or not playable or not affordable
                    else 'normal'
                ),
            )
        self.skirmish_shop_help_var.set(
            f'{side} upgrades, and only for the units your country fields. '
            'Six offers a battle, each bought once: what you buy becomes '
            'your own copy of the unit, which nobody else in the battle can '
            'build. Win a battle and six new ones are drawn -- your ally '
            'spends its own Ore on its own army the same way.'
        )
        bought = sum(purchase.stacks for purchase in run.purchases)
        ally_bought = sum(purchase.stacks for purchase in run.ally_purchases)
        self.skirmish_owned_var.set(
            f'Bought this run: {bought}'
            f'   |   ally: {ally_bought}   (hover for the list)'
        )
        self.refresh_skirmish_owned_tooltip(run)

    def refresh_skirmish_owned_tooltip(self, run):
        """Say what both armies have bought, since the ally shops unseen."""
        tooltip = getattr(self, 'skirmish_owned_tooltip', None)
        if tooltip is None:
            return
        ally = country_by_index(run.ally_country)
        mine = purchase_labels(run.purchases, self.skirmish_country_id(run))
        theirs = purchase_labels(
            run.ally_purchases, ally.country_id if ally else ''
        )
        lines = ['Yours:'] + [f'  {line}' for line in mine or ('nothing yet',)]
        lines += [
            f'{ally.display if ally else "Ally"}:'
        ] + [f'  {line}' for line in theirs or ('nothing yet',)]
        tooltip.text = '\n'.join(lines)

    def skirmish_upgrade_at(self, index):
        shelf = getattr(self, '_skirmish_shelf', ())
        return shelf[index] if 0 <= index < len(shelf) else None

    def refresh_skirmish_shop_buttons(self, _event=None):
        """Kept for the callers that repaint after a launch or a save."""
        run = self.skirmish_run
        if run is not None and hasattr(self, 'skirmish_upgrade_cards'):
            self.refresh_skirmish_shop(run)

    def buy_skirmish_upgrade(self, index):
        run = self.skirmish_run
        upgrade = self.skirmish_upgrade_at(index)
        if run is None or upgrade is None:
            return
        if self.skirmish_launch_blocked():
            self.skirmish_message_var.set('Wait for the running game to close.')
            return
        try:
            run = buy_upgrade(run, upgrade)
        except SkirmishTransitionError as exc:
            self.skirmish_message_var.set(str(exc))
            return
        self.skirmish_run = self.skirmish_repository.save_run(run)
        log_event(
            'skirmish_upgrade_bought',
            run_id=run.run_id,
            unit=upgrade.unit,
            buff_type=upgrade.buff_type,
            price=upgrade.price,
            coins_left=run.coins,
        )
        self.skirmish_message_var.set(
            f'Bought {upgrade.name} for {upgrade.price} Ore.'
        )
        self.refresh_skirmish_mode()

    # -- the saved runs ---------------------------------------------------

    def refresh_skirmish_run_window(self):
        window = getattr(self, '_skirmish_run_window', None)
        if window is None or not window.winfo_exists():
            return
        tree = self.skirmish_run_tree
        selected = set(tree.selection())
        tree.delete(*tree.get_children())
        runs, active_run_id = self.skirmish_repository.list_runs()
        for run in runs:
            tree.insert('', 'end', iid=run.run_id, values=(
                'Playing' if run.run_id == active_run_id else '',
                run_progress_text(run),
                self.skirmish_army_text(run),
                run.won_battles,
                run.status.value.title(),
                run.seed,
            ))
        restored = [
            run.run_id for run in runs if run.run_id in selected
        ] or [run.run_id for run in runs if run.run_id == active_run_id]
        if restored:
            tree.selection_set(restored)
        self.refresh_skirmish_run_buttons()

    def refresh_skirmish_run_buttons(self, _event=None):
        window = getattr(self, '_skirmish_run_window', None)
        if window is None or not window.winfo_exists():
            return
        run_id = self._selected_skirmish_run_id()
        _runs, active_run_id = self.skirmish_repository.list_runs()
        blocked = self.skirmish_launch_blocked()
        self.skirmish_resume_button.configure(
            state=(
                'normal'
                if run_id and run_id != active_run_id and not blocked
                else 'disabled'
            )
        )
        self.skirmish_delete_button.configure(
            state='normal' if run_id and not blocked else 'disabled'
        )

    def _selected_skirmish_run_id(self):
        window = getattr(self, '_skirmish_run_window', None)
        if window is None or not window.winfo_exists():
            return ''
        selection = self.skirmish_run_tree.selection()
        return selection[0] if selection else ''

    def resume_selected_skirmish_run(self):
        if self.skirmish_launch_blocked():
            self.skirmish_message_var.set('Wait for the running game to close.')
            return
        run_id = self._selected_skirmish_run_id()
        if not run_id:
            return
        try:
            run = self.skirmish_repository.select_run(run_id)
        except SkirmishPersistenceError as exc:
            self.skirmish_message_var.set(str(exc))
        else:
            self._skirmish_setup_open = False
            self.skirmish_message_var.set(
                f'Resumed the run on seed {run.seed}.'
            )
        self.refresh_skirmish_mode()

    def delete_selected_skirmish_run(self):
        if self.skirmish_launch_blocked():
            self.skirmish_message_var.set('Wait for the running game to close.')
            return
        run_id = self._selected_skirmish_run_id()
        runs, _active = self.skirmish_repository.list_runs()
        run = next((stored for stored in runs if stored.run_id == run_id), None)
        if run is None:
            return
        warning = (
            'This run is still being played.\n\n'
            if run.status is RunStatus.ACTIVE else ''
        )
        if not messagebox.askyesno(
            'Delete Skirmish Run?',
            f'{warning}Delete the run on seed {run.seed}, at '
            f'battle {run.battle}?',
            parent=self,
        ):
            return
        try:
            self.skirmish_repository.delete_run(run_id)
        except SkirmishPersistenceError as exc:
            self.skirmish_message_var.set(str(exc))
        else:
            self.skirmish_message_var.set(
                f'Deleted the run on seed {run.seed}.'
            )
        self.refresh_skirmish_mode()

    # -- the battle -------------------------------------------------------

    def skirmish_houses(self, run, offer):
        """Return the computer players, ally first, in seating order."""
        return houses_for(run, offer)

    def launch_skirmish_offer(self, index):
        if self.skirmish_launch_blocked():
            self.skirmish_message_var.set('Wait for the running game to close.')
            return
        run = self.skirmish_run
        if run is None or run.status is not RunStatus.ACTIVE:
            self.skirmish_message_var.set('Start a run first.')
            return
        try:
            run = commit_offer(run, index)
        except SkirmishTransitionError as exc:
            self.skirmish_message_var.set(str(exc))
            return
        offer = run.committed()
        entry = map_by_relative_path(offer.map_path)
        if entry is None:
            self.skirmish_message_var.set(
                f'{offer.map_name} is not installed any more.'
            )
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
        player = country_by_index(run.player_country)
        if player is None:
            self.skirmish_message_var.set(
                'This run plays a country the installed rules no longer have.'
            )
            return
        self.skirmish_run = self.skirmish_repository.save_run(run)
        try:
            battle = build_battle(
                run, offer, entry,
                # Read here rather than in the worker: these come off Tk
                # variables, and Tk is not safe to touch from another
                # thread.
                difficulty=self.get_selected_difficulty_value(),
                game_speed=self.get_selected_game_speed_value(),
            )
        except LookupError as exc:
            self.skirmish_message_var.set(f'{exc}.')
            return
        self.run_in_background(
            'Starting battle, please wait…',
            'Copying the map and writing the battle setup.',
            lambda: self.prepare_skirmish_launch_files(battle),
            lambda _result: self.start_skirmish_process(battle),
            lambda exc, detail: self.handle_skirmish_launch_error(exc, detail),
        )

    def prepare_skirmish_launch_files(self, battle):
        """Put the map and the battle setup where the spawner reads them.

        What a launch writes is the same whichever window asked for it, so
        it lives in the mode rather than here. What is still this
        controller's is the two steps around it: a generated ruleset the
        client would otherwise load has to be cleared first, and the
        difficulty has to reach the game's own options file.
        """
        prepare_battle(
            battle,
            before=lambda: (
                self.disable_generated_rules_for_client(),
                self.cleanup_generated_root_maps(),
            ),
            after=lambda: self.write_launch_options(
                battle['difficulty'], battle['game_speed']
            ),
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
            'Failed to write the battle files. See log for details.',
            parent=self,
        )
        self.refresh_skirmish_mode()

    def start_skirmish_process(self, battle):
        from randomizer.launch.syringe import windows_syringe_command_line

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
        # Where the game's log stood when this battle began. Its result is
        # read from here on, so an earlier game's score block cannot be
        # mistaken for this one's.
        try:
            battle['log_offset'] = DEBUG_LOG.stat().st_size
        except OSError:
            battle['log_offset'] = 0
        self._skirmish_launch = battle
        self.active_game_process = process
        # No hook: a skirmish has no mission markers to watch for. The
        # watcher still runs, because noticing the game has closed is what
        # ends the launch.
        self.active_hook = None
        self.active_mission_attempt = None
        entry = battle['map']
        self.append_log(
            f'Launched battle {battle["battle"]} on {entry.name} '
            f'({len(battle["houses"])} computer players) PID={process.pid}.'
        )
        log_event(
            'skirmish_process_started',
            pid=process.pid,
            run_id=battle['run_id'],
            battle=battle['battle'],
            map=entry.path.name,
            challenge=battle['offer'].challenge,
            houses=[house.country for house in battle['houses']],
            seed=battle['seed'],
            command=command_text,
        )
        self.skirmish_message_var.set(f'Fighting on {entry.name}.')
        self.refresh_skirmish_mode()
        self.poll_hook_log()

    def skirmish_result(self, battle):
        """Return how the battle ended, or ``None`` if it never finished."""
        return last_game_result(
            read_debug_log_tail(DEBUG_LOG, battle.get('log_offset', 0)),
            player_name=battle.get('player_name', SKIRMISH_PLAYER_NAME),
        )

    def finish_progression_launch_context(self):
        if not self.skirmish_launch_active():
            return super().finish_progression_launch_context()
        battle = self._skirmish_launch
        self._skirmish_launch = None
        # The staged AI file belongs to the battle that just ended. Left in
        # the game folder it would be what the client loads next time
        # somebody plays Mental Omega without this launcher.
        remove_staged_ai_file()
        entry = battle['map']
        result = self.skirmish_result(battle)
        message = self.apply_skirmish_result(battle, result)
        self.append_log(message)
        log_event(
            'skirmish_finished',
            run_id=battle['run_id'],
            battle=battle['battle'],
            map=entry.path.name,
            finished=result is not None,
            won=bool(result and result.won),
            result=result.to_dict() if result else None,
        )
        if hasattr(self, 'skirmish_battle_cards'):
            self.skirmish_message_var.set(message)
            self.refresh_skirmish_mode()

    def apply_skirmish_result(self, battle, result):
        """Record the outcome against the run that fought it."""
        entry = battle['map']
        run = self.skirmish_repository.load_run()
        if run is None or run.run_id != battle['run_id']:
            # The player switched runs while the game was up, or deleted the
            # one that was playing. The battle stands for nothing.
            return f'{entry.name} finished, but its run is no longer open.'
        # A game closed before it finished is a defeat. It cannot be
        # anything else: a battle going badly could otherwise be thrown away
        # from the menu at no cost, which is the whole of the difficulty.
        won = bool(result is not None and result.won)
        try:
            if won:
                ally = country_by_index(run.ally_country)
                run = self.offer_skirmish_battles(record_victory(
                    run,
                    ally_country=ally.country_id if ally else None,
                    result=result,
                ))
                message = (
                    f'Victory on {entry.name} — {result.kills} kills, '
                    f'{result.lost} lost, score {result.score:,}. '
                    f'Battle {run.battle} is ready.'
                )
            else:
                run = record_defeat(run, result=result)
                how = (
                    f'Defeat on {entry.name}' if result is not None
                    else f'Left {entry.name} unfinished, which counts as a '
                    'defeat'
                )
                if run.status is RunStatus.ACTIVE:
                    message = (
                        f'{how}. {run.lives_left} '
                        f'{"life" if run.lives_left == 1 else "lives"} left; '
                        'the same battle stands.'
                    )
                else:
                    # Out of lives. What it did outlives it on the board.
                    self.record_skirmish_run_end(run, 'Out of lives')
                    self.refresh_skirmish_board()
                    message = (
                        f'{how}. The run ends at battle '
                        f'{run.battle}, {run.won_battles} won.'
                    )
        except SkirmishTransitionError as exc:
            return str(exc)
        self.skirmish_run = self.skirmish_repository.save_run(run)
        return message
