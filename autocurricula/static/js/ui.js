import { $, $$, esc, state } from './state.js';
import { send } from './websocket.js';

export function switchSidebarTab(id) {
  $$('.stab').forEach(t => t.classList.toggle('active', t.dataset.pane === id));
  $$('.sidebar-pane').forEach(t => t.classList.toggle('active', t.id === id));
  if (id === 'chat-pane') {
    requestAnimationFrame(() => {
      const s = $('#chat-scroll');
      s.scrollTop = s.scrollHeight;
    });
  }
}

export function switchBottomTab(id) {
  $$('.btab').forEach(t => t.classList.toggle('active', t.dataset.panel === id));
  $$('.bottom-panel').forEach(t => t.classList.toggle('active', t.id === id));
}

export function setButtonsDisabled(off) {
  $$('.tool-btn').forEach(b => {
    b.style.opacity = off ? '.3' : '';
    b.style.pointerEvents = off ? 'none' : '';
  });
}

export function closeModal(name) {
  $(`#${name}-overlay`).classList.add('hidden');
}

export function showProblemsModal(problems) {
  const tbody = $('#problems-table tbody');
  tbody.innerHTML = '';
  if (!problems.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--t3);padding:18px">No problems yet</td></tr>';
  }
  const statusOrder = { in_progress: 0, scaffolded: 1, failed: 2, skipped: 3, solved: 4 };
  const sorted = [...problems].sort((a, b) => (statusOrder[a.status] ?? 0) - (statusOrder[b.status] ?? 0));
  sorted.forEach(p => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${esc(p.title)}</td>
      <td>${p.category}</td>
      <td><span class="d-${p.difficulty}">${p.difficulty}</span></td>
      <td><span class="s-${p.status}">${p.status.replace('_', ' ')}</span></td>
      <td>${p.attempts}</td>`;
    tr.addEventListener('click', () => {
      send({ type: 'command', name: 'replay', args: [p.id] });
      closeModal('problems');
    });
    tbody.appendChild(tr);
  });
  $('#problems-overlay').classList.remove('hidden');
}

export function showProgressModal(data) {
  let cats = '';
  for (const [cat, c] of Object.entries(data.categories || {})) {
    const pct = c.total ? (c.solved / c.total * 100) : 0;
    cats += `<div class="category-row">
      <span class="category-name">${cat}</span>
      <div class="category-bar-bg"><div class="category-bar-fill" style="width:${pct}%"></div></div>
      <span class="category-count">${c.solved}/${c.total}</span>
    </div>`;
  }
  $('#progress-content').innerHTML = `
    <div class="progress-summary">
      <div class="stat-card"><div class="stat-value" style="color:var(--green)">${data.solved}</div><div class="stat-label">Solved</div></div>
      <div class="stat-card"><div class="stat-value" style="color:var(--red)">${data.failed}</div><div class="stat-label">Failed</div></div>
      <div class="stat-card"><div class="stat-value">${data.rate}%</div><div class="stat-label">Rate</div></div>
    </div>
    ${cats || '<div style="color:var(--t3);text-align:center;padding:12px">No data yet</div>'}`;
  $('#progress-overlay').classList.remove('hidden');
}

export function showConfirmModal(msg) {
  $('#confirm-message').textContent = msg;
  $('#confirm-overlay').classList.remove('hidden');
}

export function initResize(handleId, direction) {
  const handle = $(`#${handleId}`);
  if (!handle) return;

  let startPos, startSize, target;

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    handle.classList.add('dragging');

    if (direction === 'h') {
      target = $('#sidebar');
      startPos = e.clientX;
      startSize = target.getBoundingClientRect().width;
      document.body.classList.add('resizing');
    } else {
      target = $('#bottom-bar');
      startPos = e.clientY;
      startSize = target.getBoundingClientRect().height;
      document.body.classList.add('resizing-v');
    }

    const onMove = (e) => {
      if (direction === 'h') {
        const delta = e.clientX - startPos;
        const parentW = $('#app-main').getBoundingClientRect().width;
        const newW = Math.max(200, Math.min(parentW - 300, startSize + delta));
        target.style.width = newW + 'px';
      } else {
        const delta = startPos - e.clientY;
        const parentH = $('#main-col').getBoundingClientRect().height;
        const newH = Math.max(80, Math.min(parentH - 150, startSize + delta));
        target.style.height = newH + 'px';
      }
      if (state.editor) state.editor.layout();
    };

    const onUp = () => {
      handle.classList.remove('dragging');
      document.body.classList.remove('resizing', 'resizing-v');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}

let pomoInterval = null;
let pomoEnd = 0;
let pomoBreakEnd = 0;
let pomoBreakInterval = null;

const POMO_WORK = 25 * 60;
const POMO_BREAK = 5 * 60;

function fmtTime(secs) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function startPomodoro() {
  stopPomodoro();
  pomoEnd = Date.now() + POMO_WORK * 1000;
  $('#btn-pomodoro').classList.add('active');
  pomoTick();
  pomoInterval = setInterval(pomoTick, 1000);
}

function pomoTick() {
  const left = Math.max(0, Math.ceil((pomoEnd - Date.now()) / 1000));
  $('#pomodoro-label').textContent = fmtTime(left);
  if (left <= 0) {
    clearInterval(pomoInterval);
    pomoInterval = null;
    startBreak();
  }
}

export function stopPomodoro() {
  if (pomoInterval) { clearInterval(pomoInterval); pomoInterval = null; }
  if (pomoBreakInterval) { clearInterval(pomoBreakInterval); pomoBreakInterval = null; }
  $('#btn-pomodoro').classList.remove('active');
  $('#pomodoro-label').textContent = '';
  $('#pomo-break-overlay').classList.add('hidden');
}

function startBreak() {
  pomoBreakEnd = Date.now() + POMO_BREAK * 1000;
  $('#pomo-break-overlay').classList.remove('hidden');
  breakTick();
  pomoBreakInterval = setInterval(breakTick, 1000);
}

function breakTick() {
  const left = Math.max(0, Math.ceil((pomoBreakEnd - Date.now()) / 1000));
  $('#pomo-break-timer').textContent = fmtTime(left);
  if (left <= 0) {
    endBreak();
  }
}

export function endBreak() {
  if (pomoBreakInterval) { clearInterval(pomoBreakInterval); pomoBreakInterval = null; }
  $('#pomo-break-overlay').classList.add('hidden');
  startPomodoro();
}

export function isPomodoroRunning() {
  return pomoInterval !== null;
}
