"""Skirmish Shop workspace widgets: who is playing, and where."""

from ._builder_dependencies import tk, ttk
from .scrolling import claim_wheel, scroll_owner


MAP_COLUMNS = (
    ('name', 'Map', 260),
    ('players', 'Seats', 60),
    ('modes', 'Game modes', 200),
)


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


def build_skirmish_tab(self, workspace_tabs):
    tab = ttk.Frame(workspace_tabs, padding=8)
    self.skirmish_tab = tab
    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(1, weight=1)

    setup = ttk.LabelFrame(tab, text='Battle', padding=8)
    setup.grid(row=0, column=0, sticky='ew')
    for column in (1, 3, 5, 7):
        setup.columnconfigure(column, weight=1)

    ttk.Label(setup, text='You play:').grid(row=0, column=0, sticky='w')
    self.skirmish_country_combo = _combo(
        setup, self.skirmish_country_var, (),
    )
    self.skirmish_country_combo.grid(row=0, column=1, sticky='ew', padx=(5, 12))
    ttk.Label(setup, text='Ally:').grid(row=0, column=2, sticky='w')
    self.skirmish_ally_combo = _combo(setup, self.skirmish_ally_var, ())
    self.skirmish_ally_combo.grid(row=0, column=3, sticky='ew', padx=(5, 12))
    ttk.Label(setup, text='Enemies:').grid(row=0, column=4, sticky='w')
    self.skirmish_enemy_count_combo = _combo(
        setup,
        self.skirmish_enemy_count_var,
        ('1', '2', '3'),
        width=4,
        on_change=self.refresh_skirmish_maps,
    )
    self.skirmish_enemy_count_combo.grid(
        row=0, column=5, sticky='w', padx=(5, 12)
    )
    ttk.Label(setup, text='Enemy skill:').grid(row=0, column=6, sticky='w')
    self.skirmish_handicap_combo = _combo(
        setup, self.skirmish_handicap_var, ('Easy', 'Normal', 'Hard'), width=8
    )
    self.skirmish_handicap_combo.grid(row=0, column=7, sticky='w', padx=(5, 0))
    # An ally takes a seat of its own, so how many the map needs changes with
    # it as well as with the enemy count.
    self.skirmish_ally_combo.bind(
        '<<ComboboxSelected>>', self.refresh_skirmish_maps, add='+'
    )

    body = ttk.Frame(tab)
    body.grid(row=1, column=0, sticky='nsew', pady=(8, 0))
    body.columnconfigure(0, weight=3)
    body.columnconfigure(1, weight=2)
    body.rowconfigure(1, weight=1)

    filters = ttk.Frame(body)
    filters.grid(row=0, column=0, sticky='ew', pady=(0, 6))
    filters.columnconfigure(1, weight=1)
    ttk.Label(filters, text='Search:').grid(row=0, column=0, sticky='w')
    ttk.Entry(filters, textvariable=self.skirmish_search_var).grid(
        row=0, column=1, sticky='ew', padx=(5, 0)
    )
    self.skirmish_search_var.trace_add(
        'write', lambda *_args: self.refresh_skirmish_maps()
    )

    tree_frame = ttk.Frame(body)
    tree_frame.grid(row=1, column=0, sticky='nsew', padx=(0, 8))
    tree = ttk.Treeview(
        tree_frame,
        columns=tuple(column for column, _heading, _width in MAP_COLUMNS),
        show='headings',
        selectmode='browse',
        height=14,
    )
    for column, heading, width in MAP_COLUMNS:
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
    tree.bind('<<TreeviewSelect>>', self.on_skirmish_map_selected)
    tree.bind('<Double-1>', lambda _event: self.launch_skirmish())
    self.skirmish_map_tree = tree

    preview = ttk.LabelFrame(body, text='Preview', padding=8)
    preview.grid(row=1, column=1, sticky='nsew')
    preview.columnconfigure(0, weight=1)
    preview.rowconfigure(0, weight=1)
    # The image is the map: what a player recognises is its shape, not its
    # name, so the preview the client shows is shown here too.
    self.skirmish_preview_label = ttk.Label(preview, anchor='center')
    self.skirmish_preview_label.grid(row=0, column=0, sticky='nsew')
    ttk.Label(
        preview,
        textvariable=self.skirmish_map_detail_var,
        style='Shop.Help.TLabel',
        wraplength=320,
        justify='left',
    ).grid(row=1, column=0, sticky='ew', pady=(8, 0))

    actions = ttk.Frame(tab)
    actions.grid(row=2, column=0, sticky='ew', pady=(8, 0))
    self.skirmish_launch_button = ttk.Button(
        actions,
        text='Launch Battle',
        style='Launch.TButton',
        command=self.launch_skirmish,
        state='disabled',
    )
    self.skirmish_launch_button.pack(side='left')
    ttk.Label(
        actions,
        textvariable=self.skirmish_message_var,
        justify='left',
    ).pack(side='left', padx=(12, 0))
    return tab
