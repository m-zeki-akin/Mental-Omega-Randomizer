/* Building elements without a framework, and without innerHTML.
 *
 * Everything on a screen comes from the launcher, and some of it is a map
 * name a player downloaded. Text goes in as text; nothing here ever parses
 * a string as markup. */

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') throw new Error('Elements are built, not parsed');
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on')) {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(child));
  }
  return node;
}

/** Replace everything inside a node, in one write. */
export function fill(node, children) {
  node.replaceChildren(...[].concat(children).filter(Boolean));
  return node;
}

/** A number a player might act on, with its thousands separated. */
export function count(value) {
  return Number(value || 0).toLocaleString();
}
