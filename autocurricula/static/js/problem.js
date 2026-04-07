import { $, $$, esc, state } from './state.js';
import { send } from './websocket.js';
import { renderMarkdownWithLatex, renderLatex } from './markdown.js';
import { switchSidebarTab, switchBottomTab } from './ui.js';
import { DerivationEditor } from './editor.js';

export function loadProblem(p) {
  state.currentProblem = p;
  const isDerivation = p.format === 'markdown';

  $('#top-problem').textContent = p.title;
  $('#top-difficulty').textContent = p.difficulty;
  $('#top-difficulty').className = `diff-${p.difficulty}`;

  $('#problem-md').innerHTML = renderMarkdownWithLatex(`## ${p.title}\n\n${p.question_md}`);
  $('#theory-md').innerHTML = renderMarkdownWithLatex(p.theory_md || '*No theory available.*');
  renderLatex($('#problem-md'));
  renderLatex($('#theory-md'));
  $$('.md-body a').forEach(a => { a.target = '_blank'; a.rel = 'noopener'; });

  $('#sidebar-empty').classList.add('hidden');
  const chatScroll = $('#chat-scroll');
  const typingEl = $('#typing-indicator');
  chatScroll.innerHTML = '';
  chatScroll.appendChild(typingEl);

  if (p.chat_history && p.chat_history.length) {
    p.chat_history.forEach(msg => {
      appendChat(msg.role === 'user' ? 'user' : 'claude', msg.content, false);
    });
  }

  switchSidebarTab('problem-pane');

  if (p.status === 'solved' || p.status === 'failed' || p.status === 'skipped') {
    showNextButton(null, false);
    if (p.status === 'solved') {
      if (p.user_rating) {
        const labels = ['Trivial', 'Easy', 'Medium', 'Hard', 'Brutal'];
        const row = document.createElement('div');
        row.className = 'chat-msg rating-prompt';
        row.innerHTML = `<div class="rating-label">Rated: ${labels[p.user_rating - 1]}</div>`;
        $('#chat-scroll').insertBefore(row, $('#typing-indicator'));
      } else {
        showRatingPrompt(p.id, null, false);
      }
    }
  } else {
    resetSkipButton();
  }

  $('#btn-run').classList.toggle('hidden', isDerivation);
  $('#btn-test').classList.toggle('hidden', isDerivation);

  if (p.code !== undefined) {
    if (state.editor) {
      const m = state.editor.getModel();
      if (m) {
        monaco.editor.setModelLanguage(m, isDerivation ? 'markdown' : 'python');
        state.editor.updateOptions({ wordWrap: isDerivation ? 'on' : 'off' });
        m.setValue(p.code);
      }
    } else {
      state.pendingEditorCode = p.code;
    }
  }

  if (isDerivation) {
    $('#editor-container').classList.add('hidden');
    $('#derivation-editor').classList.remove('hidden');
    $('#bottom-bar').classList.add('derivation-mode');
    $('#resize-bottom').classList.add('hidden');
    state.derivEditor = new DerivationEditor($('#derivation-editor'));
    state.derivEditor.setValue(p.code || '');
  } else {
    $('#editor-container').classList.remove('hidden');
    $('#derivation-editor').classList.add('hidden');
    $('#bottom-bar').classList.remove('derivation-mode');
    $('#resize-bottom').classList.remove('hidden');
    state.derivEditor = null;
    switchBottomTab('tests-panel');
    renderInitialTests(p.open_test_names || [], p.hidden_test_count || 0);
  }
}

export function appendOutput(content, isHtml, isError) {
  const panel = $('#output-scroll');
  const el = document.createElement('div');
  el.className = 'log-line' + (isError ? ' c-error' : '');
  if (isHtml) el.innerHTML = content;
  else el.textContent = content;
  panel.appendChild(el);
  panel.scrollTop = panel.scrollHeight;
}

export function appendChat(role, content, isHtml) {
  const panel = $('#chat-scroll');
  const el = document.createElement('div');
  if (role === 'user') {
    el.className = 'chat-msg user-msg';
    el.innerHTML = `<span class="msg-label">you</span>${esc(content).replace(/\n/g, '<br>')}`;
  } else {
    el.className = 'chat-msg claude-msg';
    const inner = document.createElement('div');
    inner.className = 'md-body';
    if (isHtml) inner.innerHTML = content;
    else inner.innerHTML = renderMarkdownWithLatex(content);
    renderLatex(inner);
    inner.querySelectorAll('a').forEach(a => { a.target = '_blank'; a.rel = 'noopener'; });
    el.appendChild(inner);
  }
  panel.insertBefore(el, $('#typing-indicator'));
  requestAnimationFrame(() => requestAnimationFrame(() => { panel.scrollTop = panel.scrollHeight; }));
}

export function showRatingPrompt(problemId, nextDifficulty, hasParent) {
  const labels = ['Trivial', 'Easy', 'Medium', 'Hard', 'Brutal'];
  const row = document.createElement('div');
  row.className = 'chat-msg rating-prompt';
  row.innerHTML = `
    <div class="rating-label">How hard was this?</div>
    <div class="rating-buttons">
      ${labels.map((l, i) => `<button class="rating-btn" data-rating="${i + 1}">${l}</button>`).join('')}
    </div>`;
  $('#chat-scroll').insertBefore(row, $('#typing-indicator'));
  const scroll = $('#chat-scroll');
  scroll.scrollTop = scroll.scrollHeight;

  row.querySelectorAll('.rating-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const rating = parseInt(btn.dataset.rating);
      send({ type: 'rate_problem', problem_id: problemId, rating });
      row.querySelectorAll('.rating-btn').forEach(b => {
        b.disabled = true;
        b.classList.toggle('selected', b === btn);
      });
      row.querySelector('.rating-label').textContent = `Rated: ${labels[rating - 1]}`;
      showNextButton(nextDifficulty, hasParent);
    });
  });
}

export function showNextButton(nextDifficulty, hasParent) {
  const btn = $('#btn-skip');
  state.pendingNext = { next_difficulty: nextDifficulty, has_parent: hasParent };
  btn.innerHTML = `
    <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M1 5.5h8M6 2l3.5 3.5L6 9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
    Next`;
  btn.classList.add('next-btn');
}

export function resetSkipButton() {
  const btn = $('#btn-skip');
  state.pendingNext = null;
  btn.innerHTML = `
    <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M1 2l4 3.5L1 9V2zM6 2l4 3.5L6 9V2z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/></svg>
    Skip`;
  btn.classList.remove('next-btn');
}

export function renderInitialTests(openNames, hiddenCount) {
  const container = $('#tests-scroll');
  container.innerHTML = '';

  const pendingIcon = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 2"/></svg>';

  const header = document.createElement('div');
  header.className = 'tests-header';
  const total = openNames.length + hiddenCount;
  header.innerHTML = `<span class="tests-badge pending">PENDING</span><span class="tests-count">${total} test${total !== 1 ? 's' : ''}</span>`;
  container.appendChild(header);

  if (openNames.length) {
    const label = document.createElement('div');
    label.className = 'tests-section-label';
    label.textContent = 'Open Tests';
    container.appendChild(label);

    openNames.forEach(name => {
      const row = document.createElement('div');
      row.className = 'test-row';
      row.innerHTML = `<div class="test-icon pending">${pendingIcon}</div><div class="test-info"><div class="test-name">${esc(name)}</div></div>`;
      container.appendChild(row);
    });
  }

  if (hiddenCount > 0) {
    const label = document.createElement('div');
    label.className = 'tests-section-label';
    label.textContent = 'Hidden Tests';
    container.appendChild(label);

    const row = document.createElement('div');
    row.className = 'test-row';
    row.innerHTML = `<div class="test-icon pending">${pendingIcon}</div><div class="test-info"><div class="test-name">${hiddenCount} hidden test${hiddenCount !== 1 ? 's' : ''}</div></div>`;
    container.appendChild(row);
  }
}

export function renderTestResults(msg) {
  const container = $('#tests-scroll');
  container.innerHTML = '';

  const passIcon = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const failIcon = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
  const errorIcon = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor" stroke-width="1.2"/><path d="M6 4v3M6 8.5v.01" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>';

  const header = document.createElement('div');
  header.className = 'tests-header';
  const badge = msg.passed ? 'pass' : 'fail';
  const badgeText = msg.passed ? 'PASS' : 'FAIL';
  header.innerHTML = `
    <span class="tests-badge ${badge}">${badgeText}</span>
    <span class="tests-count">${msg.num_passed} passed, ${msg.num_failed} failed</span>
  `;
  container.appendChild(header);

  function renderTests(tests, sectionLabel) {
    if (sectionLabel) {
      const label = document.createElement('div');
      label.className = 'tests-section-label';
      label.textContent = sectionLabel;
      container.appendChild(label);
    }
    tests.forEach(t => {
      const row = document.createElement('div');
      row.className = 'test-row';
      const isFailed = t.status !== 'passed';
      const iconClass = t.status === 'passed' ? 'pass' : t.status === 'error' ? 'error' : 'fail';
      const icon = t.status === 'passed' ? passIcon : t.status === 'error' ? errorIcon : failIcon;
      const chevron = '<svg class="test-chevron" width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M3 2l4 3-4 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

      row.innerHTML = `
        <div class="test-icon ${iconClass}">${icon}</div>
        <div class="test-info">
          <div class="test-name">${isFailed && t.detail ? chevron : ''}${esc(t.name)}</div>
          ${t.detail ? `<div class="test-detail collapsed">${esc(t.detail)}</div>` : ''}
        </div>
      `;

      if (isFailed && t.detail) {
        row.classList.add('expandable');
        row.addEventListener('click', () => {
          row.classList.toggle('expanded');
          const detail = row.querySelector('.test-detail');
          if (detail) detail.classList.toggle('collapsed');
        });
      }

      container.appendChild(row);
    });
  }

  if (msg.sections) {
    msg.sections.forEach(s => renderTests(s.tests, s.label));
  } else {
    renderTests(msg.tests);
  }
}
