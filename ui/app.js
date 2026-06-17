// AI Workout Coach — UI orchestrator.
// State lives in localStorage so a page refresh resumes the same chat.

(function () {
  const API_BASE = "/api/v1";
  const LS_CONVERSATIONS = "awc_conversations_v1";
  const LS_CURRENT = "awc_current_conv_v1";
  const LS_USER = "awc_current_user_v1";

  // ─── state ─────────────────────────────────────────────────────
  const state = {
    conversations: loadConversations(),
    currentId: localStorage.getItem(LS_CURRENT),
    userId: localStorage.getItem(LS_USER) || "user_a",
    history: [],
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
  const $userPicker = document.getElementById("user-picker");
  const $convTitle = document.getElementById("conv-title");
  const $convStatus = document.getElementById("conv-status");
  const $uploadInput = document.getElementById("upload-input");
  const $historyStatus = document.getElementById("history-status");

  // ─── init ──────────────────────────────────────────────────────
  function init() {
    renderUserPicker();
    renderConversationList();
    if (state.currentId) {
      const c = getConversation(state.currentId);
      if (c) renderConversation(c);
      else clearChat();
    } else {
      clearChat();
    }
    loadHistoryForUser(state.userId).then(updateConvStatus);
    bindEvents();
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
      userId: state.userId,
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
  function renderUserPicker() {
    window.UI.renderUserPicker($userPicker, state.userId, async (newUserId) => {
      state.userId = newUserId;
      localStorage.setItem(LS_USER, newUserId);
      await loadHistoryForUser(newUserId);
      updateConvStatus();
    });
  }

  function renderConversationList() {
    window.UI.renderConversationList(
      $convList,
      state.conversations,
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
    const parts = [`user: ${state.userId}`];
    if (state.history.length) parts.push(`${state.history.length} workouts loaded`);
    $convStatus.textContent = parts.join(" · ");
  }

  // ─── history loading ───────────────────────────────────────────
  async function loadHistoryForUser(userId) {
    if (userId === "anonymous") {
      state.history = [];
      $historyStatus.textContent = "No history (knowledge-only mode)";
      return;
    }
    $historyStatus.textContent = "Loading…";
    try {
      const r = await fetch(`${API_BASE}/sample-history?user_id=${encodeURIComponent(userId)}`);
      if (!r.ok) throw new Error(`${r.status}`);
      const data = await r.json();
      state.history = data.history || [];
      $historyStatus.textContent = `${state.history.length} ${data.name ? "(" + data.name + ")" : ""} entries`;
    } catch (e) {
      state.history = [];
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
      role: "assistant", content: "", tool_traces: [], sources: [],
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

    const body = { message: text, user_id: state.userId, history: state.history };

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
        if (event.answer && !msg.content) {
          msg.content = event.answer;
          setAnswerHTML(node, window.UI.streamHelpers.renderMarkdown(msg.content));
        }
        if (event.sources && event.sources.length) {
          msg.sources = event.sources;
          window.UI.updateAssistantSection(node, "sources", window.UI.renderCitations(msg.sources));
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
        state.userId = "custom_upload";
        localStorage.setItem(LS_USER, state.userId);
        renderUserPicker();
        $historyStatus.textContent = `Loaded ${history.length} entries from ${file.name}`;
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
