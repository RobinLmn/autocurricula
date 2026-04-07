import { $, esc, showLoading } from './state.js';
import { send } from './websocket.js';

export function showClaudeError(error) {
  let banner = $('#claude-error-banner');
  if (!error) {
    if (banner) banner.remove();
    $('#btn-new-workspace').disabled = false;
    return;
  }
  $('#btn-new-workspace').disabled = true;
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'claude-error-banner';
    const landing = $('#landing-inner');
    landing.insertBefore(banner, landing.children[1]);
  }
  banner.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1L1 13h12L7 1z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7 5.5v3M7 10.5v.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg> ${esc(error)}`;
}

export function renderWorkspaces(workspaces) {
  const grid = $('#workspaces-grid');
  grid.innerHTML = '';

  if (!workspaces.length) {
    grid.innerHTML = '<p style="text-align:center;color:var(--t3);padding:20px 0;font-size:13px">No workspaces yet. Create one to get started.</p>';
    return;
  }

  workspaces.forEach(ws => {
    const section = document.createElement('div');
    section.className = 'ws-section';

    const card = document.createElement('div');
    card.className = 'ws-card';
    card.addEventListener('click', () => {
      showLoading('Loading workspace...');
      send({ type: 'select_workspace', slug: ws.slug });
    });

    const cats = Object.keys(ws.categories || {}).slice(0, 4);
    const catPills = cats.map(c => `<span class="ws-cat-pill">${c}</span>`).join('');

    const total = ws.total || 1;
    const solvedW = Math.max(0, (ws.solved / total) * 100);
    const failedW = Math.max(0, (ws.failed / total) * 100);
    const ipW = Math.max(0, (ws.in_progress / total) * 100);

    card.innerHTML = `
      <div class="ws-card-main">
        <div class="ws-card-role">${esc(ws.role)}</div>
        <div class="ws-card-meta">
          <span>${ws.total} problem${ws.total !== 1 ? 's' : ''}</span>
          <span class="ws-stat-solved">${ws.solved} solved</span>
          <span>${ws.rate}% rate</span>
        </div>
      </div>
      <div class="ws-card-cats">${catPills}</div>
      ${ws.total > 0 ? `
      <div class="ws-card-bar">
        <div class="ws-bar-seg" style="width:${solvedW}%;background:var(--green)"></div>
        <div class="ws-bar-seg" style="width:${failedW}%;background:var(--red)"></div>
        <div class="ws-bar-seg" style="width:${ipW}%;background:var(--t3)"></div>
      </div>` : ''}
      <svg class="ws-card-arrow" width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
    `;
    section.appendChild(card);

    const history = ws.history || [];
    if (history.length) {
      const list = document.createElement('div');
      list.className = 'ws-history';
      history.forEach(p => {
        const statusIcon = p.status === 'solved'
          ? '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
          : p.status === 'failed'
          ? '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'
          : p.status === 'skipped'
          ? '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1 3l4 3-4 3V3zM6 3l4 3-4 3V3z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/></svg>'
          : '';
        const statusClass = p.status === 'solved' ? 'solved' : p.status === 'failed' ? 'failed' : p.status === 'skipped' ? 'skipped' : '';

        const row = document.createElement('div');
        row.className = 'history-row';
        row.innerHTML = `
          ${statusIcon ? `<div class="history-icon ${statusClass}">${statusIcon}</div>` : '<div class="history-icon-spacer"></div>'}
          <div class="history-title">${esc(p.title)}</div>
          <span class="history-cat">${esc(p.category)}</span>
          <span class="history-diff diff-${p.difficulty}">${esc(p.difficulty)}</span>
          <button class="history-btn history-clear" title="Clear solution and retry">Clear</button>
        `;
        row.addEventListener('click', () => {
          showLoading('Loading problem...');
          send({ type: 'load_problem', slug: ws.slug, problem_id: p.id });
        });
        row.querySelector('.history-clear').addEventListener('click', (e) => {
          e.stopPropagation();
          send({ type: 'clear_problem', slug: ws.slug, problem_id: p.id });
        });
        list.appendChild(row);
      });

      const newRow = document.createElement('div');
      newRow.className = 'history-row history-new-row';
      newRow.innerHTML = `
        <div class="history-icon" style="color:var(--t3)"><svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></div>
        <div class="history-title" style="color:var(--t3)">New problem</div>
      `;
      newRow.addEventListener('click', () => {
        send({ type: 'select_workspace', slug: ws.slug });
      });
      list.appendChild(newRow);

      section.appendChild(list);
    }

    grid.appendChild(section);
  });
}
