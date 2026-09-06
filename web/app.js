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

/** Run one launcher action and redraw, saying so if it refuses. */
export async function act(name, args = {}) {
  try {
    status('...');
    const result = await call(name, args);
    await refresh();
    return result;
  } catch (error) {
    status(error.message);
    return null;
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

function buildModeControl(modes, current, locked, lockedBy) {
  const control = document.getElementById('mode');
  if (!control) return;
  control.replaceChildren();
  for (const mode of modes) {
    const option = document.createElement('option');
    option.value = mode.name;
    option.textContent = mode.ported ? mode.name : `${mode.name} (classic)`;
    option.selected = mode.name === current;
    control.append(option);
  }
  control.disabled = Boolean(locked);
  control.title = locked ? lockedBy : 'What the launcher is set to play';
}

/**
 * Draw the launcher as the mode it is set to.
 *
 * Called at the start and whenever the mode changes -- which is the only
 * thing that changes what screens there are.
 */
export async function showMode({ keep = null } = {}) {
  const answer = await call('launcher.modes');
  buildModeControl(
    answer.modes, answer.current, answer.locked, answer.locked_by,
  );
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
  const control = document.getElementById('mode');
  if (control) {
    control.addEventListener('change', async (event) => {
      const wanted = event.target.value;
      if (await act('launcher.use_mode', { name: wanted })) {
        await showMode();
      } else {
        // Refused. The control has to go back to what is true rather
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
