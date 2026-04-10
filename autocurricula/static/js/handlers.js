import { $, state, pendingRequests, hideLoading, showLoading, updateLoadingProgress } from './state.js';
import { send } from './websocket.js';
import { initMonaco } from './editor.js';
import { showClaudeError, renderWorkspaces } from './landing.js';
import { loadProblem, appendOutput, appendChat, promoteQueuedMessages, showRatingPrompt, showNextButton, renderTestResults } from './problem.js';
import { switchSidebarTab, switchBottomTab, setButtonsDisabled, showProblemsModal, showProgressModal, showConfirmModal } from './ui.js';

export function showView(name) {
  state.currentView = name;
  $('#landing-view').classList.toggle('hidden', name !== 'landing');
  $('#app-view').classList.toggle('hidden', name !== 'app');
  if (name === 'app' && !state.editor) initMonaco();
  if (name === 'app' && state.editor) state.editor.layout();
}

export const handlers = {
  landing(msg) {
    hideLoading();
    renderWorkspaces(msg.workspaces || []);
    showClaudeError(msg.claude_error || null);
    showView('landing');
  },

  state(msg) {
    showView('app');
    if (msg.problem) {
      hideLoading();
      loadProblem(msg.problem);
    } else {
      showLoading('Generating problem...');
    }
  },

  onboarded(msg) {
    showView('app');
  },

  problem_loaded(msg) {
    hideLoading();
    loadProblem(msg.problem);
  },

  log(msg) {
    if (msg.text) appendOutput(msg.text, false, msg.error);
    else appendOutput(msg.html || '', true);
  },

  chat_response(msg) {
    appendChat('claude', msg.html || msg.text || '', !!msg.html);
    switchSidebarTab('chat-pane');
  },

  busy(msg) {
    $('#typing-indicator').classList.toggle('hidden', !msg.busy);
    setButtonsDisabled(msg.busy);
    if (!msg.busy) hideLoading();
  },

  chat_busy(msg) {
    state.chatBusy = msg.busy;
    $('#typing-indicator').classList.toggle('hidden', !msg.busy);
    if (msg.busy) {
      promoteQueuedMessages();
      switchSidebarTab('chat-pane');
      const s = $('#chat-scroll');
      requestAnimationFrame(() => { s.scrollTop = s.scrollHeight; });
    }
  },

  generating() { showLoading('Generating problem...', true); },
  generating_progress(msg) { updateLoadingProgress(msg.step, msg); },

  test_results(msg) { renderTestResults(msg); switchBottomTab('tests-panel'); },

  clear_log() { $('#output-scroll').innerHTML = ''; },

  problems_list(msg) { showProblemsModal(msg.problems); },
  progress_data(msg) { showProgressModal(msg); },
  confirm(msg) { showConfirmModal(msg.message); },

  completions_result(msg) {
    const resolve = pendingRequests[msg.id];
    if (resolve) { delete pendingRequests[msg.id]; resolve(msg); }
  },
  hover_result(msg) {
    const resolve = pendingRequests[msg.id];
    if (resolve) { delete pendingRequests[msg.id]; resolve(msg); }
  },
  signatures_result(msg) {
    const resolve = pendingRequests[msg.id];
    if (resolve) { delete pendingRequests[msg.id]; resolve(msg); }
  },

  verdict(msg) {
    const labels = { solved: 'Solved!', follow_up: 'Follow-up', retry: 'Not quite', move_on: 'Moving on' };
    const label = labels[msg.decision] || 'Review';
    appendChat('claude', `**${label}**\n\n${msg.feedback}`, false);
    switchSidebarTab('chat-pane');

    if (msg.decision === 'solved') {
      showRatingPrompt(msg.problem_id, msg.next_difficulty, msg.has_parent);
    } else if (msg.decision === 'move_on') {
      showNextButton(msg.next_difficulty, msg.has_parent);
    }
  },

  error(msg) {
    hideLoading();
    appendOutput(msg.message, false, true);
  },
};
