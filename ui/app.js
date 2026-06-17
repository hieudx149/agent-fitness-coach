// AI Workout Coach — UI orchestrator.
// State lives in localStorage so a page refresh resumes the same chat.

(function () {
  const API_BASE = "/api/v1";
  const LS_CONVERSATIONS = "awc_conversations_v2";
  const LS_CURRENT = "awc_current_conv_v2";
  const LS_ROLE = "awc_role_v2";
  const LS_TARGET = "awc_target_v2";

  // ─── state ─────────────────────────────────────────────────────
  const state = {
    conversations: loadConversations(),
    currentId: localStorage.getItem(LS_CURRENT),
    role: localStorage.getItem(LS_ROLE) || "gymer",
    targetId: localStorage.getItem(LS_TARGET) || "gymer_alex",
    roster: { coaches: [], gymers: [] },
    history: [],
    profileName: null,
    profile: null,
    inFlight: false,
  };

  // DOM refs
  const $messages = document.getElementById("messages");
  const $emptyState = document.getElementById("empty-state");
  const $form = document.getElementById("chat-form");
  const $input = document.getElementById("chat-input");
  const $sendBtn = document.getElementById("send-btn");
  const $newChatBtn = document.getElementById("new-chat-btn");
  const $convList = document.getElementById("conv-list");
  const $rolePicker = document.getElementById("role-picker");
  const $targetPicker = document.getElementById("target-picker");
  const $convTitle = document.getElementById("conv-title");
  const $convStatus = document.getElementById("conv-status");
  const $uploadInput = document.getElementById("upload-input");
  const $historyStatus = document.getElementById("history-status");

  // ─── init ──────────────────────────────────────────────────────
  async function init() {
    await loadRoster();
    if (!isValidTargetForRole(state.role, state.targetId)) {
      state.targetId = defaultTargetForRole(state.role);
      localStorage.setItem(LS_TARGET, state.targetId);
    }
    renderRolePicker();
    renderTargetPicker();
    renderConversationList();
    if (state.currentId) {
      const c = getConversation(state.currentId);
      if (c && c.contextId === currentContextId()) {
        renderConversation(c);
      } else {
        state.currentId = null;
        localStorage.removeItem(LS_CURRENT);
        clearChat();
      }
    } else {
      clearChat();
    }
    await loadHistoryForTarget(state.targetId);
    updateConvStatus();
    bindEvents();
  }

  function currentContextId() {
    return `${state.role}:${state.targetId}`;
  }

  function targetsForRole(role) {
    if (role === "coach") {
      // Coach picks among the active coach's clients.
      // Currently one coach in the roster; pull its client list.
      const coach = state.roster.coaches[0];
      return coach ? coach.clients : [];
    }
    return state.roster.gymers;
  }

  function isValidTargetForRole(role, targetId) {
    return targetsForRole(role).some((t) => t.id === targetId);
  }

  function defaultTargetForRole(role) {
    const list = targetsForRole(role);
    return list.length ? list[0].id : "";
  }

  async function loadRoster() {
    try {
      const r = await fetch(`${API_BASE}/users`);
      if (!r.ok) throw new Error(r.statusText);
      state.roster = await r.json();
    } catch (e) {
      console.error("Failed to load roster", e);
      state.roster = { coaches: [], gymers: [] };
    }
  }

  // ─── conversation persistence ──────────────────────────────────
  function loadConversations() {
    try {
      return JSON.parse(localStorage.getItem(LS_CONVERSATIONS) || "[]");
    } catch {
      return [];
    }
  }

  function saveConversations() {
    localStorage.setItem(LS_CONVERSATIONS, JSON.stringify(state.conversations));
  }

  function getConversation(id) {
    return state.conversations.find((c) => c.id === id);
  }

  function createConversation(firstUserMessage) {
    const id = "c_" + Date.now() + "_" + Math.random().toString(36).slice(2, 7);
    const title = firstUserMessage.slice(0, 60) + (firstUserMessage.length > 60 ? "…" : "");
    const conv = {
      id,
      title,
      role: state.role,
      targetId: state.targetId,
      contextId: currentContextId(),
      messages: [],
      createdAt: new Date().toISOString(),
    };
    state.conversations.push(conv);
    state.currentId = id;
    localStorage.setItem(LS_CURRENT, id);
    saveConversations();
    return conv;
  }

  function deleteConversation(id) {
    state.conversations = state.conversations.filter((c) => c.id !== id);
    saveConversations();
    if (state.currentId === id) {
      state.currentId = null;
      localStorage.removeItem(LS_CURRENT);
      clearChat();
    }
    renderConversationList();
  }

  // ─── rendering ─────────────────────────────────────────────────
  function renderRolePicker() {
    window.UI.renderRolePicker($rolePicker, state.role, async (newRole) => {
      if (newRole === state.role) return;
      state.role = newRole;
      localStorage.setItem(LS_ROLE, newRole);
      // Reset target to the first valid one for this role.
      state.targetId = defaultTargetForRole(newRole);
      localStorage.setItem(LS_TARGET, state.targetId);
      renderTargetPicker();
      renderConversationList();
      state.currentId = null;
      localStorage.removeItem(LS_CURRENT);
      clearChat();
      await loadHistoryForTarget(state.targetId);
      updateConvStatus();
    });
  }

  function renderTargetPicker() {
    const targets = targetsForRole(state.role);
    window.UI.renderTargetPicker(
      $targetPicker,
      state.role,
      targets,
      state.targetId,
      async (newTargetId) => {
        if (newTargetId === state.targetId) return;
        state.targetId = newTargetId;
        localStorage.setItem(LS_TARGET, newTargetId);
        renderConversationList();
        state.currentId = null;
        localStorage.removeItem(LS_CURRENT);
        clearChat();
        await loadHistoryForTarget(newTargetId);
        updateConvStatus();
      },
    );
  }

  function conversationsForCurrentContext() {
    const ctx = currentContextId();
    return state.conversations.filter((c) => c.contextId === ctx);
  }

  function renderConversationList() {
    window.UI.renderConversationList(
      $convList,
      conversationsForCurrentContext(),
      state.currentId,
      {
        onLoad: (id) => {
          state.currentId = id;
          localStorage.setItem(LS_CURRENT, id);
          const c = getConversation(id);
          if (c) {
            renderConversation(c);
            renderConversationList();
          }
        },
        onDelete: deleteConversation,
      },
    );
  }

  function renderConversation(conv) {
    $convTitle.textContent = conv.title || "Conversation";
    $messages.innerHTML = "";
    conv.messages.forEach((m) => appendMessage(m, false));
    updateConvStatus();
  }

  function clearChat() {
    $convTitle.textContent = "New conversation";
    $messages.innerHTML = "";
    $messages.appendChild($emptyState);
    $emptyState.classList.remove("hidden");
  }

  function appendMessage(msg, persist = true) {
    if ($emptyState && !$emptyState.classList.contains("hidden")) {
      $emptyState.classList.add("hidden");
    }
    const wrapper = document.createElement("div");
    wrapper.innerHTML = window.UI.renderMessage(msg);
    const node = wrapper.firstElementChild;
    if (!node) return;
    $messages.appendChild(node);
    window.UI.bindMessage(node);
    $messages.scrollTop = $messages.scrollHeight;
    if (persist && state.currentId) {
      const c = getConversation(state.currentId);
      if (c) {
        c.messages.push(msg);
        saveConversations();
      }
    }
  }

  function showTyping() {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = window.UI.renderTypingPlaceholder();
    const node = wrapper.firstElementChild;
    node.id = "typing-placeholder";
    $messages.appendChild(node);
    $messages.scrollTop = $messages.scrollHeight;
  }

  function hideTyping() {
    const el = document.getElementById("typing-placeholder");
    if (el) el.remove();
  }

  function updateConvStatus() {
    const targetName = targetNameFor(state.targetId);
    const parts = [
      state.role === "coach" ? `Coach · client: ${targetName}` : `Gymer · ${targetName}`,
    ];
    if (state.history.length) parts.push(`${state.history.length} workouts loaded`);
    else parts.push("no history");
    $convStatus.textContent = parts.join(" · ");
  }

  function targetNameFor(targetId) {
    const list = targetsForRole(state.role);
    const found = list.find((t) => t.id === targetId);
    return found ? found.name : targetId;
  }

  // ─── history loading ───────────────────────────────────────────
  async function loadHistoryForTarget(targetId) {
    if (!targetId) {
      state.history = [];
      state.profileName = null;
      state.profile = null;
      $historyStatus.textContent = "No target selected";
      return;
    }
    $historyStatus.textContent = "Loading…";
    try {
      const r = await fetch(`${API_BASE}/sample-history?user_id=${encodeURIComponent(targetId)}`);
      if (!r.ok) throw new Error(`${r.status}`);
      const data = await r.json();
      state.history = data.history || [];
      state.profileName = data.name || null;
      state.profile = data.profile || null;
      if (state.history.length === 0) {
        $historyStatus.textContent = `No workout history (knowledge-only mode)`;
      } else {
        $historyStatus.textContent = `${state.history.length} workouts loaded`;
      }
    } catch (e) {
      state.history = [];
      state.profileName = null;
      state.profile = null;
      $historyStatus.textContent = `Failed to load: ${e.message}`;
    }
  }

  // ─── chat send (streaming) ─────────────────────────────────────
  async function sendMessage(text) {
    if (state.inFlight) return;
    if (!text.trim()) return;
    state.inFlight = true;
    $sendBtn.disabled = true;

    const userMsg = { role: "user", content: text };
    if (!state.currentId) {
      createConversation(text);
      renderConversationList();
    }
    appendMessage(userMsg);
    const c = getConversation(state.currentId);
    if (c && c.messages.length === 1 && c.title !== text.slice(0, 60)) {
      c.title = text.slice(0, 60) + (text.length > 60 ? "…" : "");
      saveConversations();
      renderConversationList();
      $convTitle.textContent = c.title;
    }

    // Create empty assistant message, then update in place as events arrive.
    const assistantMsg = {
      role: "assistant", content: "", tool_traces: [], sources: [], data_points: [],
      refused: false, refusal_category: null,
    };
    if ($emptyState && !$emptyState.classList.contains("hidden")) {
      $emptyState.classList.add("hidden");
    }
    const wrapper = document.createElement("div");
    wrapper.innerHTML = window.UI.renderMessage(assistantMsg);
    const msgNode = wrapper.firstElementChild;
    $messages.appendChild(msgNode);
    window.UI.bindMessage(msgNode);

    // Show a small "thinking…" placeholder inside the answer section
    setAnswerHTML(msgNode, `<span class="text-slate-400 text-sm">
      <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
      <span class="ml-2">Thinking…</span></span>`);

    const body = {
      message: text,
      user_id: state.targetId,
      name: state.profileName,
      profile: state.profile,
      history: state.history,
    };

    try {
      const r = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok || !r.body) {
        const errText = await r.text().catch(() => "");
        assistantMsg.content = `**Error ${r.status}**: ${errText.slice(0, 500) || r.statusText}`;
        setAnswerHTML(msgNode, window.UI.streamHelpers.renderMarkdown(assistantMsg.content));
        return;
      }

      await consumeStream(r.body, assistantMsg, msgNode);
    } catch (e) {
      assistantMsg.content = `**Network error**: ${e.message}. Is the API running at \`${API_BASE}\`?`;
      setAnswerHTML(msgNode, window.UI.streamHelpers.renderMarkdown(assistantMsg.content));
    } finally {
      // Persist the assistant message to localStorage
      const conv = getConversation(state.currentId);
      if (conv) {
        conv.messages.push(assistantMsg);
        saveConversations();
      }
      state.inFlight = false;
      $sendBtn.disabled = false;
      $input.focus();
    }
  }

  function setAnswerHTML(msgNode, html) {
    const el = msgNode.querySelector('[data-section="answer"]');
    if (el) el.innerHTML = html;
  }

  async function consumeStream(stream, msg, node) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let firstDelta = true;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // leftover partial line
      for (const line of lines) {
        if (!line.trim()) continue;
        let event;
        try {
          event = JSON.parse(line);
        } catch (e) {
          console.warn("Bad NDJSON line:", line, e);
          continue;
        }
        handleStreamEvent(event, msg, node, () => {
          if (firstDelta) {
            // Clear the "Thinking…" placeholder the first time real content arrives
            setAnswerHTML(node, "");
            firstDelta = false;
          }
        });
      }
    }
    // Flush any remaining buffered partial line
    if (buffer.trim()) {
      try {
        handleStreamEvent(JSON.parse(buffer), msg, node, () => {});
      } catch {
        // ignore — final partial often empty
      }
    }
  }

  function handleStreamEvent(event, msg, node, onFirstContent) {
    switch (event.type) {
      case "guardrail":
        if (event.refused) {
          msg.refused = true;
          msg.refusal_category = event.category;
          msg.content = event.answer || "";
          window.UI.updateAssistantSection(node, "badges", window.UI.streamHelpers.renderRefusedBadge(msg));
          setAnswerHTML(node, window.UI.streamHelpers.renderMarkdown(msg.content));
        }
        break;

      case "tool_call":
        msg.tool_traces.push({
          tool_name: event.tool_name,
          args: event.args || {},
          result_summary: "Running…",
          result_detail: null,
        });
        window.UI.updateAssistantSection(node, "traces", window.UI.renderToolTraces(msg.tool_traces));
        break;

      case "tool_result": {
        const idx = msg.tool_traces.findLastIndex
          ? msg.tool_traces.findLastIndex(
              (t) => t.tool_name === event.tool_name && t.result_summary === "Running…",
            )
          : findLastIndexCompat(
              msg.tool_traces,
              (t) => t.tool_name === event.tool_name && t.result_summary === "Running…",
            );
        if (idx >= 0) {
          msg.tool_traces[idx] = {
            ...msg.tool_traces[idx],
            result_summary: event.summary,
            result_detail: event.detail || null,
          };
        }
        window.UI.updateAssistantSection(node, "traces", window.UI.renderToolTraces(msg.tool_traces));
        break;
      }

      case "delta":
        if (event.text) {
          onFirstContent();
          msg.content += event.text;
          setAnswerHTML(node, window.UI.streamHelpers.renderMarkdown(msg.content));
        }
        break;

      case "done":
        // Re-render from the canonical answer even if we streamed deltas: the
        // final text has its [n] citations renumbered to match the score-sorted
        // source cards, so the streamed (pre-sort) numbering must be replaced.
        if (event.answer) {
          msg.content = event.answer;
          setAnswerHTML(node, window.UI.streamHelpers.renderMarkdown(msg.content));
        }
        if (event.sources && event.sources.length) {
          msg.sources = event.sources;
          window.UI.updateAssistantSection(node, "sources", window.UI.renderCitations(msg.sources));
        }
        if (event.data_points && event.data_points.length) {
          msg.data_points = event.data_points;
          window.UI.updateAssistantSection(node, "data", window.UI.renderDataPoints(msg.data_points));
        }
        if (event.usage) msg.usage = event.usage;
        if (event.iterations != null) msg.iterations = event.iterations;
        window.UI.updateAssistantSection(node, "usage", window.UI.streamHelpers.renderUsageBlock(msg));
        break;

      case "error":
        msg.content = `**Error**: ${event.message}`;
        setAnswerHTML(node, window.UI.streamHelpers.renderMarkdown(msg.content));
        break;
    }
    $messages.scrollTop = $messages.scrollHeight;
  }

  function findLastIndexCompat(arr, predicate) {
    for (let i = arr.length - 1; i >= 0; i--) if (predicate(arr[i])) return i;
    return -1;
  }

  // ─── event wiring ──────────────────────────────────────────────
  function bindEvents() {
    $form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = $input.value;
      $input.value = "";
      sendMessage(text);
    });

    $input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        $form.dispatchEvent(new Event("submit"));
      }
    });

    // Auto-grow textarea
    $input.addEventListener("input", () => {
      $input.style.height = "auto";
      $input.style.height = Math.min($input.scrollHeight, 160) + "px";
    });

    $newChatBtn.addEventListener("click", () => {
      state.currentId = null;
      localStorage.removeItem(LS_CURRENT);
      clearChat();
      renderConversationList();
      $input.focus();
    });

    $uploadInput.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const history = await window.UI.parseUploadedHistory(file);
        state.history = history;
        // Uploaded files carry no profile metadata — clear the target's.
        state.profileName = null;
        state.profile = null;
        $historyStatus.textContent = `Loaded ${history.length} entries from ${file.name} (overrides current target)`;
        updateConvStatus();
      } catch (err) {
        $historyStatus.textContent = `Upload failed: ${err.message}`;
      } finally {
        $uploadInput.value = "";
      }
    });
  }

  // boot
  document.addEventListener("DOMContentLoaded", init);
})();
