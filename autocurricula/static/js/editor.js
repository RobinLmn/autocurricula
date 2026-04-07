import { $, state, pendingRequests } from './state.js';
import { send } from './websocket.js';
import { renderMarkdownWithLatex, renderLatex } from './markdown.js';

export class DerivationEditor {
  constructor(container) {
    this.container = container;
    this.blocks = [''];
    this.activeIdx = -1;
    this.syncTimeout = null;
    this.container.innerHTML = '';
    this._render();
    this.container.addEventListener('click', (e) => {
      if (e.target === this.container) {
        this._activate(this.blocks.length - 1);
      }
    });
  }

  getValue() {
    return this.blocks.join('\n\n');
  }

  setValue(text) {
    this.blocks = text ? text.split(/\n\n+/) : [''];
    if (this.blocks.length === 0) this.blocks = [''];
    this.activeIdx = -1;
    this._render();
  }

  _render() {
    this.container.innerHTML = '';
    this.blocks.forEach((raw, i) => {
      const block = document.createElement('div');
      block.className = 'de-block';
      block.dataset.idx = i;

      if (i === this.activeIdx) {
        block.classList.add('editing');
        const ta = document.createElement('textarea');
        ta.value = raw;
        ta.spellcheck = false;
        ta.addEventListener('input', () => this._onEdit(i, ta));
        ta.addEventListener('keydown', (e) => this._onKey(e, i, ta));
        ta.addEventListener('blur', () => this._deactivate(i, ta));
        block.appendChild(ta);
        this.container.appendChild(block);
        requestAnimationFrame(() => {
          this._autosize(ta);
          ta.focus();
        });
      } else {
        block.classList.add('rendered');
        const content = document.createElement('div');
        content.className = 'rendered-content md-body';
        if (raw.trim()) {
          content.innerHTML = renderMarkdownWithLatex(raw);
          this.container.appendChild(block);
          block.appendChild(content);
          renderLatex(content);
        } else {
          content.innerHTML = '<span class="de-empty-hint">Click to start writing...</span>';
          block.appendChild(content);
          this.container.appendChild(block);
        }
        block.addEventListener('click', () => this._activate(i));
      }
    });
  }

  _activate(idx) {
    if (idx === this.activeIdx) return;
    this.activeIdx = idx;
    this._render();
  }

  _deactivate(idx, ta) {
    this.blocks[idx] = ta.value;
    this.blocks = this.blocks.filter((b, i) => b.trim() || i === 0);
    if (this.blocks.length === 0) this.blocks = [''];
    this.activeIdx = -1;
    this._render();
    this._sync();
  }

  _onEdit(idx, ta) {
    this.blocks[idx] = ta.value;
    this._autosize(ta);
    clearTimeout(this.syncTimeout);
    this.syncTimeout = setTimeout(() => this._sync(), 800);
  }

  _onKey(e, idx, ta) {
    if (e.key === 'Enter' && !e.shiftKey) {
      const val = ta.value;
      const pos = ta.selectionStart;
      const before = val.substring(0, pos);
      if (before.endsWith('\n') || before === '') {
        e.preventDefault();
        const blockBefore = before.replace(/\n$/, '');
        const blockAfter = val.substring(pos);
        this.blocks[idx] = blockBefore;
        this.blocks.splice(idx + 1, 0, blockAfter);
        this.activeIdx = idx + 1;
        this._render();
        this._sync();
        return;
      }
    }
    if (e.key === 'Backspace' && ta.selectionStart === 0 && ta.selectionEnd === 0 && idx > 0) {
      e.preventDefault();
      const prevLen = this.blocks[idx - 1].length;
      this.blocks[idx - 1] += '\n' + this.blocks[idx];
      this.blocks.splice(idx, 1);
      this.activeIdx = idx - 1;
      this._render();
      const newTa = this.container.querySelector('.de-block.editing textarea');
      if (newTa) {
        newTa.selectionStart = newTa.selectionEnd = prevLen + 1;
      }
      this._sync();
      return;
    }
    if (e.key === 'ArrowUp' && ta.selectionStart === 0 && idx > 0) {
      e.preventDefault();
      this.blocks[idx] = ta.value;
      this._activate(idx - 1);
    }
    if (e.key === 'ArrowDown' && ta.selectionStart === ta.value.length && idx < this.blocks.length - 1) {
      e.preventDefault();
      this.blocks[idx] = ta.value;
      this._activate(idx + 1);
    }
  }

  _autosize(ta) {
    ta.style.height = 'auto';
    ta.style.height = ta.scrollHeight + 'px';
  }

  _sync() {
    send({ type: 'code_sync', code: this.getValue() });
  }
}

export function initMonaco() {
  require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs' } });

  require(['vs/editor/editor.main'], function () {
    monaco.editor.defineTheme('autocurricula', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: '',                foreground: 'e6edf3', background: '161616' },
        { token: 'comment',         foreground: '6e7681', fontStyle: 'italic' },
        { token: 'keyword',         foreground: 'c9a0dc' },
        { token: 'keyword.control', foreground: 'c9a0dc' },
        { token: 'string',          foreground: 'e89b9b' },
        { token: 'string.escape',   foreground: 'd4976c' },
        { token: 'number',          foreground: '79c0ff' },
        { token: 'type',            foreground: 'ff9e64' },
        { token: 'type.identifier', foreground: 'ff9e64' },
        { token: 'function',        foreground: '7dcfff' },
        { token: 'variable',        foreground: 'e6edf3' },
        { token: 'operator',        foreground: '89929b' },
        { token: 'delimiter',       foreground: '6e7681' },
        { token: 'delimiter.parenthesis', foreground: '89929b' },
        { token: 'delimiter.bracket',     foreground: '89929b' },
        { token: 'decorator',       foreground: 'c9a0dc' },
        { token: 'identifier',      foreground: 'e6edf3' },
        { token: 'constant',        foreground: '79c0ff' },
        { token: 'tag',             foreground: '7ee787' },
        { token: 'attribute.name',  foreground: '79c0ff' },
      ],
      colors: {
        'editor.background':                   '#161616',
        'editor.foreground':                   '#c8c8c8',
        'editor.lineHighlightBackground':      '#1c1c1c',
        'editor.selectionBackground':          '#ffffff15',
        'editor.inactiveSelectionBackground':   '#ffffff0b',
        'editorCursor.foreground':              '#e0e0e0',
        'editorLineNumber.foreground':          '#2a2a2a',
        'editorLineNumber.activeForeground':    '#505050',
        'editor.selectionHighlightBackground':  '#ffffff08',
        'editorIndentGuide.background':         '#1e1e1e',
        'editorIndentGuide.activeBackground':   '#2a2a2a',
        'editorWidget.background':              '#1a1a1a',
        'editorWidget.border':                  '#242424',
        'input.background':                    '#1a1a1a',
        'input.border':                        '#2a2a2a',
        'scrollbar.shadow':                    '#00000000',
        'scrollbarSlider.background':           '#ffffff08',
        'scrollbarSlider.hoverBackground':      '#ffffff12',
        'scrollbarSlider.activeBackground':     '#ffffff1a',
        'minimap.background':                  '#161616',
      },
    });

    state.editor = monaco.editor.create($('#editor-container'), {
      value: '',
      language: 'python',
      theme: 'autocurricula',
      fontFamily: "'JetBrains Mono', 'SF Mono', 'Menlo', monospace",
      fontSize: 13,
      lineHeight: 22,
      padding: { top: 16, bottom: 16 },
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      renderLineHighlight: 'line',
      cursorBlinking: 'smooth',
      cursorSmoothCaretAnimation: 'on',
      cursorWidth: 1,
      smoothScrolling: true,
      bracketPairColorization: { enabled: false },
      matchBrackets: 'near',
      guides: { indentation: true, bracketPairs: false },
      overviewRulerBorder: false,
      hideCursorInOverviewRuler: true,
      overviewRulerLanes: 0,
      scrollbar: {
        vertical: 'auto',
        horizontal: 'auto',
        verticalScrollbarSize: 5,
        horizontalScrollbarSize: 5,
      },
      wordWrap: 'off',
      tabSize: 2,
      insertSpaces: true,
      automaticLayout: true,
      renderWhitespace: 'none',
      fixedOverflowWidgets: true,
      folding: true,
      glyphMargin: false,
      lineDecorationsWidth: 0,
      lineNumbersMinChars: 3,
    });

    if (state.pendingEditorCode !== null) {
      const m = state.editor.getModel();
      if (state.currentProblem && state.currentProblem.format === 'markdown') {
        monaco.editor.setModelLanguage(m, 'markdown');
      }
      m.setValue(state.pendingEditorCode);
      state.pendingEditorCode = null;
    }

    state.editor.onDidChangeModelContent(() => {
      clearTimeout(state.syncTimeout);
      const val = state.editor.getValue();
      state.syncTimeout = setTimeout(() => {
        send({ type: 'code_sync', code: val });
      }, 800);
    });

    const KIND_MAP = {
      Function: monaco.languages.CompletionItemKind.Function,
      Class: monaco.languages.CompletionItemKind.Class,
      Module: monaco.languages.CompletionItemKind.Module,
      Variable: monaco.languages.CompletionItemKind.Variable,
      Keyword: monaco.languages.CompletionItemKind.Keyword,
      Property: monaco.languages.CompletionItemKind.Property,
      File: monaco.languages.CompletionItemKind.File,
    };

    function requestIntellisense(type, model, position) {
      return new Promise((resolve) => {
        const reqId = type[0] + '-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
        send({
          type,
          source: model.getValue(),
          line: position.lineNumber,
          column: position.column,
          id: reqId,
        });
        pendingRequests[reqId] = resolve;
        setTimeout(() => {
          if (pendingRequests[reqId]) {
            delete pendingRequests[reqId];
            resolve(null);
          }
        }, 4000);
      });
    }

    // Completions
    monaco.languages.registerCompletionItemProvider('python', {
      triggerCharacters: ['.'],
      provideCompletionItems: async (model, position) => {
        if (!state.autocompleteEnabled) return { suggestions: [] };
        const msg = await requestIntellisense('completions', model, position);
        if (!msg || !msg.items || !msg.items.length) return { suggestions: [] };

        const word = model.getWordUntilPosition(position);
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: position.column,
        };

        return {
          suggestions: msg.items.map(item => {
            let docValue = item.doc || '';
            if (item.doc_url) docValue += `\n\n[Open documentation](${item.doc_url})`;
            return {
              label: item.name,
              kind: KIND_MAP[item.kind] || monaco.languages.CompletionItemKind.Variable,
              detail: item.detail,
              documentation: docValue ? { value: docValue, isTrusted: true, supportHtml: true } : undefined,
              insertText: item.name,
              range,
            };
          }),
        };
      },
    });

    // Hover
    monaco.languages.registerHoverProvider('python', {
      provideHover: async (model, position) => {
        if (!state.autocompleteEnabled) return null;
        const word = model.getWordAtPosition(position);
        if (!word) return null;

        const msg = await requestIntellisense('hover', model, position);
        if (!msg || !msg.content) return null;

        const c = msg.content;
        const parts = [];
        if (c.signature) parts.push({ value: '```python\n' + c.signature + '\n```' });
        let docBlock = c.doc || '';
        if (c.doc_url) docBlock += `\n\n[Open documentation](${c.doc_url})`;
        if (docBlock) parts.push({ value: docBlock, isTrusted: true, supportHtml: true });

        return {
          range: new monaco.Range(
            position.lineNumber, word.startColumn,
            position.lineNumber, word.endColumn
          ),
          contents: parts,
        };
      },
    });

    // Ctrl+Click → open documentation
    monaco.languages.registerDefinitionProvider('python', {
      provideDefinition: async (model, position) => {
        const word = model.getWordAtPosition(position);
        if (!word) return null;
        const msg = await requestIntellisense('hover', model, position);
        if (!msg || !msg.content || !msg.content.doc_url) return null;
        window.open(msg.content.doc_url, '_blank');
        return null;
      },
    });

    // Signature help
    monaco.languages.registerSignatureHelpProvider('python', {
      signatureHelpTriggerCharacters: ['(', ','],
      provideSignatureHelp: async (model, position) => {
        if (!state.autocompleteEnabled) return null;
        const msg = await requestIntellisense('signatures', model, position);
        if (!msg || !msg.signatures || !msg.signatures.length) return null;

        return {
          value: {
            signatures: msg.signatures.map(s => ({
              label: `${s.name}(${s.params.map(p => p.name).join(', ')})`,
              documentation: s.doc || '',
              parameters: s.params.map(p => ({
                label: p.name,
                documentation: p.description || '',
              })),
            })),
            activeSignature: 0,
            activeParameter: msg.signatures[0].index || 0,
          },
          dispose: () => {},
        };
      },
    });
  });
}
