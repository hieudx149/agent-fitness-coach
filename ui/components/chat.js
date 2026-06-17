// Renders chat messages — user bubbles right, assistant blocks left with
// tool-trace cards above the final markdown answer + citation cards below.

window.UI = window.UI || {};

window.UI.renderMessage = function (msg) {
  if (msg.role === "user") return renderUser(msg);
  if (msg.role === "assistant") return renderAssistant(msg);
  if (msg.role === "system") return ""; // not displayed
  return "";
};

window.UI.renderTypingPlaceholder = function () {
  return `
    <div class="flex justify-start" data-typing>
      <div class="max-w-2xl md:max-w-3xl w-full">
        <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1 pl-1">🤖 Agent</div>
        <div class="rounded-lg bg-white border border-slate-200 px-4 py-3 text-slate-500 text-sm">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="ml-2">Thinking…</span>
        </div>
      </div>
    </div>
  `;
};

function renderUser(msg) {
  return `
    <div class="flex flex-col items-end">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1 pr-1">🙂 Human</div>
      <div class="max-w-md md:max-w-xl rounded-lg bg-brand-500 text-white px-4 py-2.5 text-sm whitespace-pre-wrap break-words">
        ${escapeHtml(msg.content)}
      </div>
    </div>
  `;
}

function renderAssistant(msg) {
  const refusedBadge = msg.refused
    ? `<div class="inline-flex items-center gap-1 mb-2 text-[11px] font-medium px-2 py-0.5 rounded bg-amber-100 text-amber-800">
         🛡 Refused · ${escapeHtml(msg.refusal_category || "")}
       </div>`
    : "";

  const traces = window.UI.renderToolTraces(msg.tool_traces || []);
  const answer = renderMarkdown(msg.content || "");
  const citations = window.UI.renderCitations(msg.sources || []);

  const usage = msg.usage
    ? `<div class="text-[10px] text-slate-400 mt-2">tokens: prompt ${msg.usage.prompt_tokens} / completion ${msg.usage.completion_tokens} · iterations: ${msg.iterations ?? "—"}</div>`
    : "";

  return `
    <div class="flex justify-start">
      <div class="max-w-2xl md:max-w-3xl w-full">
        <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1 pl-1">🤖 Agent</div>
        ${refusedBadge}
        ${traces}
        <div class="markdown bg-white border border-slate-200 rounded-lg px-4 py-3 mt-2 text-slate-800">
          ${answer || "<i class='text-slate-400'>(empty response)</i>"}
        </div>
        ${citations}
        ${usage}
      </div>
    </div>
  `;
};

window.UI.bindMessage = function (msgEl) {
  window.UI.bindToolToggles(msgEl);
  window.UI.bindCitationToggles(msgEl);
};

function renderMarkdown(md) {
  if (!md) return "";
  const html = window.marked.parse(md, { breaks: true });
  return window.DOMPurify.sanitize(html);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
