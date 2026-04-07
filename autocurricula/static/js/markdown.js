export function renderMarkdownWithLatex(text) {
  const blocks = [];
  let i = 0;

  function stash(match) {
    const id = i++;
    blocks.push(match);
    return `<math-placeholder data-id="${id}"></math-placeholder>`;
  }

  // Display: $$ ... $$ (can span lines)
  text = text.replace(/\$\$([\s\S]*?)\$\$/g, stash);
  // Display: \[ ... \] (can span lines)
  text = text.replace(/\\\[([\s\S]*?)\\\]/g, stash);
  // Inline: \( ... \)
  text = text.replace(/\\\((.*?)\\\)/g, stash);
  // Inline: $ ... $ (not $$, content can include backslashes)
  text = text.replace(/(?<!\$)\$(?!\$)([^\$]+?)\$(?!\$)/g, stash);

  let html = marked.parse(text);

  html = html.replace(/<math-placeholder data-id="(\d+)"><\/math-placeholder>/g, (_, id) => {
    return blocks[parseInt(id)];
  });

  return html;
}

export function renderLatex(el) {
  if (typeof renderMathInElement !== 'function') {
    setTimeout(() => renderLatex(el), 200);
    return;
  }
  renderMathInElement(el, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false },
      { left: '\\[', right: '\\]', display: true },
      { left: '\\(', right: '\\)', display: false },
    ],
    throwOnError: false,
  });
}
