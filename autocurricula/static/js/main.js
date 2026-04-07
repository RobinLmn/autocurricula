import { $, $$, state, showLoading } from './state.js';
import { setHandlers, connect, send } from './websocket.js';
import { handlers } from './handlers.js';
import { appendChat } from './problem.js';
import {
  switchSidebarTab,
  switchBottomTab,
  closeModal,
  initResize,
  startPomodoro,
  stopPomodoro,
  endBreak,
  isPomodoroRunning,
} from './ui.js';

function handleInput(val) {
  const line = val.trim();
  if (!line) return;
  const code = state.editor ? state.editor.getValue() : '';

  if (line.startsWith('/')) {
    const parts = line.slice(1).split(/\s+/);
    send({ type: 'command', name: parts[0], args: parts.slice(1), code });
  } else {
    appendChat('user', line);
    send({ type: 'chat', message: line, code });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setHandlers(handlers);
  connect();

  // Sidebar tabs
  $$('.stab').forEach(t => t.addEventListener('click', () => switchSidebarTab(t.dataset.pane)));

  // Bottom tabs
  $$('.btab').forEach(t => t.addEventListener('click', () => switchBottomTab(t.dataset.panel)));

  // Input
  const input = $('#command-input');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
      e.preventDefault();
      handleInput(input.value);
      input.value = '';
      input.style.height = 'auto';
    }
  });
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });

  // Toolbar buttons
  const cmd = (name) => () => send({ type: 'command', name, code: state.editor ? state.editor.getValue() : '' });
  const cmdWithOutput = (name) => () => { switchBottomTab('output-panel'); cmd(name)(); };
  $('#btn-run').addEventListener('click', cmdWithOutput('run'));
  $('#btn-test').addEventListener('click', cmd('test'));
  $('#btn-submit').addEventListener('click', () => { cmd('submit')(); switchSidebarTab('chat-pane'); });
  $('#btn-scaffold').addEventListener('click', cmd('scaffold'));
  $('#btn-skip').addEventListener('click', () => {
    if (state.pendingNext) {
      send({ type: 'next_problem', ...state.pendingNext });
    } else {
      cmd('give-up')();
    }
  });

  // Home button
  $('#btn-home').addEventListener('click', () => send({ type: 'go_home' }));

  // Pomodoro
  $('#btn-pomodoro').addEventListener('click', () => {
    if (isPomodoroRunning()) stopPomodoro();
    else startPomodoro();
  });
  $('#pomo-break-skip').addEventListener('click', endBreak);

  // Autocomplete toggle
  const acBtn = $('#btn-autocomplete');
  acBtn.classList.add('active');
  acBtn.addEventListener('click', () => {
    state.autocompleteEnabled = !state.autocompleteEnabled;
    acBtn.classList.toggle('active', state.autocompleteEnabled);
  });

  // Create workspace
  $('#btn-new-workspace').addEventListener('click', () => {
    $('#create-form').classList.remove('hidden');
    $('#btn-new-workspace').classList.add('hidden');
    setTimeout(() => $('#create-input').focus(), 60);
  });

  $('#create-cancel').addEventListener('click', () => {
    $('#create-form').classList.add('hidden');
    $('#btn-new-workspace').classList.remove('hidden');
  });

  function submitCreateWorkspace() {
    const val = $('#create-input').value.trim();
    if (val) {
      showLoading('Creating workspace...');
      send({ type: 'create_workspace', role: val });
      $('#create-input').value = '';
      $('#create-form').classList.add('hidden');
      $('#btn-new-workspace').classList.remove('hidden');
    }
  }

  $('#create-confirm').addEventListener('click', submitCreateWorkspace);

  $('#create-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      submitCreateWorkspace();
    } else if (e.key === 'Escape') {
      $('#create-form').classList.add('hidden');
      $('#btn-new-workspace').classList.remove('hidden');
    }
  });

  // Confirm modal
  $('#confirm-yes').addEventListener('click', () => {
    send({ type: 'confirm_response', confirmed: true });
    closeModal('confirm');
  });
  $('#confirm-no').addEventListener('click', () => {
    send({ type: 'confirm_response', confirmed: false });
    closeModal('confirm');
  });

  // Modal close buttons (replace inline onclick)
  $$('.modal-close').forEach(btn => {
    const overlay = btn.closest('.overlay');
    if (overlay) {
      btn.addEventListener('click', () => overlay.classList.add('hidden'));
    }
  });

  // Close overlays on backdrop click
  $$('.overlay').forEach(o => o.addEventListener('click', (e) => {
    if (e.target !== o) return;
    o.classList.add('hidden');
    if (o.id === 'confirm-overlay') send({ type: 'confirm_response', confirmed: false });
  }));

  // Resize handles
  initResize('resize-sidebar', 'h');
  initResize('resize-bottom', 'v');

  // Global keys
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      $$('.overlay:not(.hidden)').forEach(o => {
        o.classList.add('hidden');
        if (o.id === 'confirm-overlay') send({ type: 'confirm_response', confirmed: false });
      });
    }
  });
});
