"""Skirmish Shop workspace widgets: the run, and the battles it offers."""

from randomizer.skirmish.model import BATTLES_PER_TIER

from ._builder_dependencies import WidgetTooltip, tk, ttk
from .scrolling import claim_wheel, scroll_owner
from .windows import center_on_pointer


BATTLE_CARDS = 3
RUN_COLUMNS = (
    ('playing', '', 60),
    ('progress', 'Progress', 200),
    ('army', 'Army', 190),
    ('won', 'Battles won', 90),
    ('status', 'Status', 80),
    ('seed', 'Seed', 130),
)
# The shop's offers, laid out the way the battles are. A table with an
# Owned column made sense when an upgrade could be bought many times; one
# that is bought once needs to show what it does and what it costs, and to
# stay put when it is bought.
SHELF_COLUMNS = 3
SHELF_ROWS = 2


def _combo(parent, variable, values, width=26, on_change=None):
    box = ttk.Combobox(
        parent,
        textvariable=variable,
        values=values,
        state='readonly',
        width=width,
    )
    claim_wheel(box)
    if on_change is not None:
        box.bind('<<ComboboxSelected>>', on_change)
    return box


def open_skirmish_run_window(self, _event=None):
    """Open every saved run in a list of its own."""
    window = getattr(self, '_skirmish_run_window', None)
    if window is not None and window.winfo_exists():
        window.deiconify()
        self.refresh_skirmish_run_window()
        center_on_pointer(self, window)
        window.lift()
        window.focus_set()
        return window
    window = tk.Toplevel(self)
    window.title('Saved Skirmish Runs')
    window.transient(self)
    frame = ttk.Frame(window, padding=12)
    frame.grid(row=0, column=0, sticky='nsew')
    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)
    ttk.Label(
        frame,
        text=(
            'Every run you have saved. Runs never affect each other: each '
            'one keeps its own army, its own battles and its own Ore. '
            'Resume one to make it the run the launcher plays.'
        ),
        style='Muted.TLabel',
        wraplength=560,
        justify='left',
    ).grid(row=0, column=0, sticky='ew', pady=(0, 8))
    tree_frame = ttk.Frame(frame)
    tree_frame.grid(row=1, column=0, sticky='nsew')
    tree = ttk.Treeview(
        tree_frame,
        columns=tuple(column for column, _heading, _width in RUN_COLUMNS),
        show='headings',
        selectmode='browse',
        height=8,
    )
    for column, heading, width in RUN_COLUMNS:
        tree.heading(column, text=heading)
        tree.column(column, width=width, minwidth=50, stretch=True)
    scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.grid(row=0, column=0, sticky='nsew')
    scrollbar.grid(row=0, column=1, sticky='ns')
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)
    scroll_owner(tree_frame, target=tree, units=3)
    for widget in (tree, scrollbar):
        claim_wheel(widget)
    tree.bind('<Double-1>', lambda _event: self.resume_selected_skirmish_run())
    tree.bind('<<TreeviewSelect>>', self.refresh_skirmish_run_buttons)
    self.skirmish_run_tree = tree
    buttons = ttk.Frame(frame)
    buttons.grid(row=2, column=0, sticky='ew', pady=(8, 0))
    self.skirmish_resume_button = ttk.Button(
        buttons,
        text='Resume Run',
        command=self.resume_selected_skirmish_run,
        state='disabled',
    )
    self.skirmish_resume_button.pack(side='left')
    self.skirmish_delete_button = ttk.Button(
        buttons,
        text='Delete Run',
        style='Danger.TButton',
        command=self.delete_selected_skirmish_run,
        state='disabled',
    )
    self.skirmish_delete_button.pack(side='left', padx=(6, 0))
    ttk.Button(buttons, text='Close', command=window.destroy).pack(side='right')
    self._skirmish_run_window = window
    self.refresh_skirmish_run_window()
    center_on_pointer(self, window)
    window.lift()
    window.focus_set()
    return window


def _build_setup(self, parent):
    """The panel shown between runs: choose an army and start."""
    setup = ttk.LabelFrame(parent, text='New Run', padding=8)
    self.skirmish_setup_frame = setup
    setup.columnconfigure(1, weight=1)
    setup.columnconfigure(3, weight=1)
    ttk.Label(
        setup,
        text=(
            'Your army and your ally are chosen once and stand for the whole '
            'run -- the same country twice is fine. Which battles you are '
            'offered, how many enemies they hold and whether your ally is '
            'beside you are the run\'s business from then on -- every '
            f'{BATTLES_PER_TIER}th battle is a challenge, fought on a '
            'challenge map with no choice of which.'
        ),
        style='Muted.TLabel',
        wraplength=620,
        justify='left',
    ).grid(row=0, column=0, columnspan=4, sticky='ew', pady=(0, 8))
    ttk.Label(setup, text='You play:').grid(row=1, column=0, sticky='w')
    self.skirmish_country_combo = _combo(setup, self.skirmish_country_var, ())
    self.skirmish_country_combo.grid(row=1, column=1, sticky='ew', padx=(5, 12))
    ttk.Label(setup, text='Ally:').grid(row=1, column=2, sticky='w')
    self.skirmish_ally_combo = _combo(setup, self.skirmish_ally_var, ())
    self.skirmish_ally_combo.grid(row=1, column=3, sticky='ew', padx=(5, 12))
    self.skirmish_start_button = ttk.Button(
        setup,
        text='Start Run',
        style='Launch.TButton',
        command=self.start_skirmish_run,
    )
    self.skirmish_start_button.grid(row=1, column=4, sticky='e')
    return setup


def _build_run_header(self, parent):
    """The row shown while a run is being played."""
    header = ttk.Frame(parent)
    self.skirmish_header_frame = header
    header.columnconfigure(5, weight=1)
    ttk.Label(
        header,
        textvariable=self.skirmish_progress_var,
        font=('Segoe UI', 10, 'bold'),
        style='Shop.Stage.TLabel',
    ).grid(row=0, column=0, sticky='w', padx=(0, 12))
    ttk.Label(
        header,
        textvariable=self.skirmish_army_var,
        style='Shop.Help.TLabel',
    ).grid(row=0, column=1, sticky='w', padx=(0, 12))
    ttk.Label(
        header,
        textvariable=self.skirmish_ore_var,
        font=('Segoe UI', 10, 'bold'),
        style='Shop.Ore.TLabel',
    ).grid(row=0, column=4, sticky='w', padx=(0, 12))
    self.skirmish_run_list_button = ttk.Button(
        header,
        text='Saved Runs...',
        command=lambda: open_skirmish_run_window(self),
    )
    self.skirmish_run_list_button.grid(row=0, column=2, sticky='w', padx=(0, 4))
    self.skirmish_give_up_button = ttk.Button(
        header,
        text='Give Up Run',
        style='Danger.TButton',
        command=self.give_up_skirmish_run,
    )
    self.skirmish_give_up_button.grid(row=0, column=3, sticky='w')
    # Shown only during the warmup, which is the only thing it skips.
    self.skirmish_skip_button = ttk.Button(
        header,
        text='Skip Warmup',
        command=self.skip_skirmish_warmup,
    )
    self.skirmish_skip_button.grid(row=0, column=6, sticky='e')
    return header


def _build_battle_cards(self, parent):
    cards = ttk.Frame(parent)
    self.skirmish_cards_frame = cards
    for column in range(BATTLE_CARDS):
        cards.columnconfigure(column, weight=1, uniform='skirmish_battles')
    cards.rowconfigure(0, weight=1)
    self.skirmish_battle_cards = []
    for index in range(BATTLE_CARDS):
        card = ttk.LabelFrame(cards, text=f'Battle {index + 1}', padding=8)
        card.grid(
            row=0, column=index, sticky='nsew',
            padx=(0 if index == 0 else 6, 0),
        )
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        name_var = tk.StringVar(value='')
        detail_var = tk.StringVar(value='')
        name_label = ttk.Label(
            card,
            textvariable=name_var,
            font=('Segoe UI', 10, 'bold'),
            justify='left',
            wraplength=280,
        )
        name_label.grid(row=0, column=0, sticky='ew')
        # The map is recognised by its shape long before its name.
        preview_label = ttk.Label(card, anchor='center')
        preview_label.grid(row=1, column=0, sticky='nsew', pady=(6, 6))
        detail_label = ttk.Label(
            card,
            textvariable=detail_var,
            style='Shop.Help.TLabel',
            wraplength=280,
            justify='left',
        )
        detail_label.grid(row=2, column=0, sticky='ew', pady=(0, 7))
        launch_button = ttk.Button(
            card,
            text='Fight This Battle',
            style='Launch.TButton',
            state='disabled',
            command=lambda chosen=index: self.launch_skirmish_offer(chosen),
        )
        launch_button.grid(row=3, column=0, sticky='ew')
        self.skirmish_battle_cards.append({
            'frame': card,
            'name': name_var,
            'detail': detail_var,
            'preview_label': preview_label,
            'launch_button': launch_button,
            'tooltip': WidgetTooltip(card, ''),
        })
    return cards


def _build_shop(self, parent):
    """The upgrades on offer between battles, one card each."""
    shop = ttk.LabelFrame(parent, text='Upgrades', padding=8)
    self.skirmish_shop_frame = shop
    ttk.Label(
        shop,
        textvariable=self.skirmish_shop_help_var,
        style='Muted.TLabel',
        wraplength=620,
        justify='left',
    ).grid(row=0, column=0, columnspan=SHELF_COLUMNS, sticky='ew', pady=(0, 8))
    for column in range(SHELF_COLUMNS):
        shop.columnconfigure(column, weight=1, uniform='skirmish_upgrades')
    self.skirmish_upgrade_cards = []
    for index in range(SHELF_COLUMNS * SHELF_ROWS):
        row, column = divmod(index, SHELF_COLUMNS)
        card = ttk.Frame(shop, padding=8, relief='groove', borderwidth=1)
        card.grid(
            row=1 + row, column=column, sticky='nsew',
            padx=(0 if column == 0 else 6, 0),
            pady=(0 if row == 0 else 6, 0),
        )
        card.columnconfigure(0, weight=1)
        name_var = tk.StringVar(value='')
        effect_var = tk.StringVar(value='')
        price_var = tk.StringVar(value='')
        ttk.Label(
            card,
            textvariable=name_var,
            font=('Segoe UI', 9, 'bold'),
            wraplength=210,
            justify='left',
        ).grid(row=0, column=0, columnspan=2, sticky='ew')
        ttk.Label(
            card,
            textvariable=effect_var,
            style='Shop.Help.TLabel',
            wraplength=210,
            justify='left',
        ).grid(row=1, column=0, columnspan=2, sticky='ew', pady=(2, 6))
        ttk.Label(
            card,
            textvariable=price_var,
            font=('Segoe UI', 9, 'bold'),
            style='Shop.Ore.TLabel',
        ).grid(row=2, column=0, sticky='w')
        button = ttk.Button(
            card,
            text='Buy',
            width=9,
            command=lambda chosen=index: self.buy_skirmish_upgrade(chosen),
        )
        button.grid(row=2, column=1, sticky='e')
        self.skirmish_upgrade_cards.append({
            'frame': card,
            'name': name_var,
            'effect': effect_var,
            'price': price_var,
            'button': button,
            'tooltip': WidgetTooltip(card, ''),
        })
    footer = ttk.Frame(shop)
    footer.grid(
        row=1 + SHELF_ROWS, column=0, columnspan=SHELF_COLUMNS,
        sticky='ew', pady=(8, 0),
    )
    footer.columnconfigure(0, weight=1)
    owned_label = ttk.Label(
        footer,
        textvariable=self.skirmish_owned_var,
        style='Shop.Help.TLabel',
        justify='left',
    )
    owned_label.grid(row=0, column=0, sticky='w')
    # The ally shops on its own, so what it bought is only visible here.
    self.skirmish_owned_tooltip = WidgetTooltip(owned_label, '')
    return shop


def build_skirmish_tab(self, workspace_tabs):
    tab = ttk.Frame(workspace_tabs, padding=8)
    self.skirmish_tab = tab
    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(2, weight=1)

    _build_setup(self, tab)
    _build_run_header(self, tab)
    _build_battle_cards(self, tab)
    _build_shop(self, tab)

    actions = ttk.Frame(tab)
    actions.grid(row=4, column=0, sticky='ew', pady=(8, 0))
    self.skirmish_new_run_button = ttk.Button(
        actions,
        text='New Run',
        command=self.open_skirmish_setup,
    )
    self.skirmish_new_run_button.pack(side='left')
    ttk.Label(
        actions,
        textvariable=self.skirmish_message_var,
        justify='left',
    ).pack(side='left', padx=(12, 0))
    return tab
