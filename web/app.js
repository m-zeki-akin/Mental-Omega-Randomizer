/* The shell: how a screen reaches the launcher, and which one is showing. */

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

const views = new Map();
let showing = null;

/** Register one screen under the tab that opens it. */
export function register(name, view) {
  views.set(name, view);
}

/** Show one screen, and tell it to draw itself. */
export async function show(name) {
  if (!views.has(name)) return;
  showing = name;
  for (const [id, view] of views) {
    const selected = id === name;
    view.root.hidden = !selected;
    const tab = document.querySelector(`.tab[data-view="${id}"]`);
    if (tab) tab.setAttribute('aria-selected', String(selected));
  }
  await refresh();
}

/** Redraw whatever is showing. Every action ends here. */
export async function refresh() {
  const view = views.get(showing);
  if (!view) return;
  try {
    await view.render();
    status('');
  } catch (error) {
    view.root.replaceChildren(errorNotice(error));
    status(error.message);
  }
}

function errorNotice(error) {
  const node = document.createElement('div');
  node.className = 'notice notice--error';
  node.textContent = error.message || String(error);
  return node;
}

/** What the launcher is doing, in the title bar. */
export function status(text) {
  const node = document.getElementById('status');
  if (node) node.textContent = text || '';
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

function start() {
  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => show(tab.dataset.view));
  }
  const first = document.querySelector('.tab');
  show(first ? first.dataset.view : null);
}

/* pywebview says when the bridge is up. Nothing is asked before that:
 * a screen drawn without the launcher behind it is a screen showing
 * nothing with no way to say why. */
window.addEventListener('pywebviewready', start);
