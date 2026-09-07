/* The shell: how a screen reaches the launcher, and which one is showing.
 *
 * Three things live here and nothing else does: the one call a page may
 * make, the mode -- which decides what screens exist -- and the screens
 * themselves. A view owns what it draws; it does not own where it is drawn
 * or when, and it never reaches into this page for its own container. */

/**
 * Ask the launcher for something.
 *
 * The reply always has the same shape, so this is the only place that
 * knows it. A caller gets the result or an Error carrying what went
 * wrong -- never a half-answer it has to test.
 */
export async function call(name, args = {}) {
  if (!window.pywebview || !window.pywebview.api) {
    throw Object.assign(
      new Error('The launcher is not listening yet'),
      { kind: 'NoBridge' },
    );
  }
  const reply = await window.pywebview.api.call(name, args);
  if (!reply || reply.ok !== true) {
    throw Object.assign(
      new Error((reply && reply.error) || `${name} failed`),
      { kind: (reply && reply.kind) || 'Unknown' },
    );
  }
  return reply.result;
}

/* What each view draws, by name. A view registers once, at load; which
 * mode shows it is not its business. */
const views = new Map();
/* The panel each shown screen draws into, by name. Built when the mode's
 * tabs are, thrown away when the mode changes. */
const panels = new Map();
let showing = null;

/** Register one screen's drawing under the name the mode table uses. */
export function register(name, render) {
  views.set(name, render);
}

/** What the launcher is doing, in the title bar. */
export function status(text) {
  const node = document.getElementById('status');
  if (node) node.textContent = text || '';
}

function errorNotice(error) {
  const node = document.createElement('div');
  node.className = 'notice notice--error';
  node.textContent = error.message || String(error);
  return node;
}

/** Show one of the current mode's screens, and tell it to draw itself. */
export async function show(name) {
  if (!panels.has(name)) return;
  showing = name;
  for (const [id, panel] of panels) {
    const selected = id === name;
    panel.hidden = !selected;
    const tab = document.querySelector(`.tab[data-view="${id}"]`);
    if (tab) tab.setAttribute('aria-selected', String(selected));
  }
  await refresh();
}

/** Redraw whatever is showing. Every action ends here. */
export async function refresh() {
  const render = views.get(showing);
  const panel = panels.get(showing);
  if (!render || !panel) return;
  try {
    await render(panel);
    status('');
  } catch (error) {
    panel.replaceChildren(errorNotice(error));
    status(error.message);
  }
}

/* Whether a press is still landing.
 *
 * One press at a time. A change is sent, the launcher answers, and the
 * screen is drawn again from that answer -- so a second press arriving
 * before the answer decides from a screen that is already out of date.
 * Where a control sends a whole list, that is a change lost: adding two
 * units to an exclusion list quickly would send the second list without
 * the first unit in it, and the launcher would keep exactly what it was
 * told. The turned-away press leaves the title bar saying the launcher
 * is working, which it is. */
let pressing = false;

/** Run one launcher action and redraw, saying so if it refuses. */
export async function act(name, args = {}) {
  if (pressing) return null;
  pressing = true;
  try {
    status('...');
    const result = await call(name, args);
    await refresh();
    return result;
  } catch (error) {
    status(error.message);
    return null;
  } finally {
    pressing = false;
  }
}

/* --- the mode, and the screens it has -------------------------------- */

/**
 * Build the tabs and the panels one mode is drawn as.
 *
 * A screen the mode does not have is not hidden, it is not built: a panel
 * left behind would still be in the page for a view to draw into and for a
 * player to reach with a keyboard.
 */
function buildScreens(screens) {
  const tabs = document.getElementById('tabs');
  const main = document.getElementById('screens');
  if (!tabs || !main) return;
  tabs.replaceChildren();
  main.replaceChildren();
  panels.clear();
  for (const screen of screens) {
    if (!views.has(screen.name)) continue;
    const tab = document.createElement('button');
    tab.className = 'tab';
    tab.type = 'button';
    tab.setAttribute('role', 'tab');
    tab.dataset.view = screen.name;
    tab.setAttribute('aria-selected', 'false');
    tab.textContent = screen.label;
    tab.addEventListener('click', () => show(screen.name));
    tabs.append(tab);

    const panel = document.createElement('div');
    panel.className = 'screen';
    panel.id = `view-${screen.name}`;
    panel.setAttribute('role', 'tabpanel');
    panel.hidden = true;
    main.append(panel);
    panels.set(screen.name, panel);
  }
}

/** Fill one select with `{value, label, selected}` and say why it is off. */
function fillControl(id, options, { locked, lockedBy, title }) {
  const control = document.getElementById(id);
  if (!control) return;
  control.replaceChildren();
  for (const option of options) {
    const node = document.createElement('option');
    node.value = option.value;
    node.textContent = option.label;
    node.selected = Boolean(option.selected);
    control.append(node);
  }
  control.disabled = Boolean(locked);
  control.title = locked ? lockedBy : title;
}

/**
 * The mode, as two controls: which kind of game, then which one of it.
 *
 * The second is filled from the kind that is standing rather than from
 * every mode there is -- five modes offered flat is a list to read, not a
 * choice to make. Both send the same action: what the launcher is set to
 * play is one decision however it is pointed at.
 */
function buildModeControl(answer) {
  const { families = [], family, current, locked, locked_by: lockedBy } = answer;
  const standing = families.find((entry) => entry.name === family)
    || families[0] || { modes: [] };
  fillControl('family', families.map((entry) => ({
    value: entry.name,
    label: entry.name,
    selected: entry.name === standing.name,
  })), { locked, lockedBy, title: 'Which kind of game' });
  fillControl('mode', standing.modes.map((mode) => ({
    value: mode.name,
    label: mode.ported ? mode.label : `${mode.label} (classic)`,
    selected: mode.name === current,
  })), { locked, lockedBy, title: standing.description || 'Which one of it' });
}

/**
 * Draw the launcher as the mode it is set to.
 *
 * Called at the start and whenever the mode changes -- which is the only
 * thing that changes what screens there are.
 */
export async function showMode({ keep = null } = {}) {
  const answer = await call('launcher.modes');
  buildModeControl(answer);
  buildScreens(answer.screens);
  const wanted = keep && panels.has(keep) ? keep : (answer.screens[0] || {}).name;
  await show(wanted);
  return answer;
}

/** Draw the launcher light or dark, as the player keeps it. */
export async function applyTheme(theme) {
  const wanted = theme
    || (await call('launcher.appearance').catch(() => ({}))).theme;
  document.documentElement.setAttribute('data-theme', wanted || 'dark');
}

async function start() {
  // Both controls ask for the same thing: a kind of game means the first
  // mode of that kind, a mode means itself.
  for (const id of ['family', 'mode']) {
    const control = document.getElementById(id);
    if (!control) continue;
    control.addEventListener('change', async (event) => {
      const wanted = event.target.value;
      if (await act('launcher.use_mode', { name: wanted })) {
        await showMode();
      } else {
        // Refused. The controls have to go back to what is true rather
        // than sit on a mode the launcher is not in.
        await showMode({ keep: showing });
      }
    });
  }
  try {
    await applyTheme();
    await showMode();
  } catch (error) {
    status(error.message);
  }
}

/* pywebview says when the bridge is up. Nothing is asked before that:
 * a screen drawn without the launcher behind it is a screen showing
 * nothing with no way to say why. */
window.addEventListener('pywebviewready', start);
