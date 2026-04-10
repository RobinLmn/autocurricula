import { $, esc, showLoading } from './state.js';
import { send } from './websocket.js';

const TAG_COLORS = [
  '#528bff', '#2fce6b', '#f0c526', '#f04438', '#a78bfa',
  '#f97316', '#06b6d4', '#ec4899', '#84cc16', '#8b5cf6',
  '#14b8a6', '#e879f9', '#eab308', '#6366f1', '#fb923c',
];

function renderPieChart(tags, size = 80) {
  const entries = Object.entries(tags).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return '';
  const total = entries.reduce((s, e) => s + e[1], 0);
  const r = size / 2;
  const cx = r, cy = r;
  const ir = r * 0.55;

  let paths = '';
  let angle = -Math.PI / 2;
  entries.forEach(([tag, count], i) => {
    const sweep = (count / total) * Math.PI * 2;
    const color = TAG_COLORS[i % TAG_COLORS.length];
    if (sweep >= Math.PI * 2 - 0.001) {
      // Full circle — arc with identical endpoints is invisible, use two semicircles
      paths += `<path d="M${cx},${cy - r} A${r},${r} 0 1 1 ${cx},${cy + r} A${r},${r} 0 1 1 ${cx},${cy - r} L${cx},${cy - ir} A${ir},${ir} 0 1 0 ${cx},${cy + ir} A${ir},${ir} 0 1 0 ${cx},${cy - ir}Z" fill="${color}"><title>${tag}: ${count}</title></path>`;
    } else {
      const large = sweep > Math.PI ? 1 : 0;
      const x1 = cx + r * Math.cos(angle);
      const y1 = cy + r * Math.sin(angle);
      const x2 = cx + r * Math.cos(angle + sweep);
      const y2 = cy + r * Math.sin(angle + sweep);
      const ix1 = cx + ir * Math.cos(angle);
      const iy1 = cy + ir * Math.sin(angle);
      const ix2 = cx + ir * Math.cos(angle + sweep);
      const iy2 = cy + ir * Math.sin(angle + sweep);
      paths += `<path d="M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2} L${ix2},${iy2} A${ir},${ir} 0 ${large} 0 ${ix1},${iy1}Z" fill="${color}"><title>${tag}: ${count}</title></path>`;
    }
    angle += sweep;
  });

  const legend = entries.slice(0, 6).map(([tag], i) =>
    `<span class="pie-legend-item">${esc(tag)}<span class="pie-dot" style="background:${TAG_COLORS[i % TAG_COLORS.length]}"></span></span>`
  ).join('');

  return `<div class="ws-pie-wrap">
    <div class="pie-legend">${legend}</div>
    <svg class="ws-pie" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${paths}</svg>
  </div>`;
}

function formatTokens(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(n);
}

export function renderUsage24h(usage) {
  const el = $('#landing-usage');
  if (!el) return;
  if (!usage || usage.total_tokens === 0) {
    el.classList.add('hidden');
    return;
  }
  el.textContent = `${formatTokens(usage.total_tokens)} tokens in the last 24h`;
  el.classList.remove('hidden');
}

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

    const tags = ws.tags || {};
    const pieHtml = renderPieChart(tags);

    card.innerHTML = `
      <div class="ws-card-main">
        <div class="ws-card-role">${esc(ws.role)}</div>
        <div class="ws-card-meta">
          <span>${ws.total} problem${ws.total !== 1 ? 's' : ''}</span>
          <span class="ws-stat-solved">${ws.solved} solved</span>
          <span>${ws.rate}% rate</span>
        </div>
        ${ws.total ? `<div class="ws-card-bar">${
          ws.solved ? `<div class="ws-bar-seg" style="flex:${ws.solved};background:var(--green)"></div>` : ''}${
          ws.failed ? `<div class="ws-bar-seg" style="flex:${ws.failed};background:var(--red)"></div>` : ''}${
          ws.in_progress ? `<div class="ws-bar-seg" style="flex:${ws.in_progress};background:var(--yellow)"></div>` : ''}${
          (ws.total - ws.solved - ws.failed - ws.in_progress) > 0 ? `<div class="ws-bar-seg" style="flex:${ws.total - ws.solved - ws.failed - ws.in_progress};background:rgba(255,255,255,.08)"></div>` : ''
        }</div>` : ''}
      </div>
      ${pieHtml}
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
          ${(p.tags || [])[0] ? `<span class="history-tag">${esc(p.tags[0])}</span>` : ''}
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
        const existing = list.querySelector('.new-problem-prompt');
        if (existing) { existing.remove(); return; }
        const promptRow = document.createElement('div');
        promptRow.className = 'history-row new-problem-prompt';
        promptRow.innerHTML = `
          <input type="text" class="new-problem-input" placeholder="e.g. &quot;tree problem&quot; or leave blank for auto" autofocus>
          <button class="new-problem-go">Go</button>
        `;
        promptRow.addEventListener('click', e => e.stopPropagation());
        const input = promptRow.querySelector('input');
        const go = promptRow.querySelector('.new-problem-go');
        const submit = () => {
          const prompt = input.value.trim();
          showLoading('Generating problem...', true);
          send({ type: 'select_workspace', slug: ws.slug, new_problem: true, prompt });
        };
        go.addEventListener('click', submit);
        input.addEventListener('keydown', e => { if (e.key === 'Enter') submit(); });
        newRow.after(promptRow);
        input.focus();
      });
      list.appendChild(newRow);

      section.appendChild(list);
    }

    grid.appendChild(section);
  });
}
