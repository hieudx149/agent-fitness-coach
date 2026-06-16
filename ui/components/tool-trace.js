// Renders Perplexity-style inline tool traces — one collapsible card per
// tool call, shown BEFORE the assistant's final answer.

window.UI = window.UI || {};

const TOOL_META = {
  rag_search: { icon: "🔎", label: "Knowledge search", description: "Searching fitness knowledge base" },
  analyze_history: { icon: "📊", label: "Workout analysis", description: "Analyzing your training history" },
};

window.UI.renderToolTraces = function (traces) {
  if (!traces || traces.length === 0) return "";
  return (
    `<div class="mt-2 space-y-1.5">` +
    traces.map((t, i) => renderOne(t, i)).join("") +
    `</div>`
  );
};

function renderOne(trace, idx) {
  const meta = TOOL_META[trace.tool_name] || {
    icon: "🛠️",
    label: trace.tool_name,
    description: "",
  };
  const argsPreview = JSON.stringify(trace.args || {}, null, 2);
  const detailBody = renderDetail(trace);

  return `
    <div class="tool-card collapsed" data-tool-card>
      <div class="tool-card-header" data-toggle="body">
        <span>${meta.icon}</span>
        <span class="font-medium text-slate-800">${meta.label}</span>
        <span class="text-slate-500 text-xs">— ${escapeHtml(trace.result_summary || "")}</span>
        <span class="ml-auto text-slate-400 text-[11px]">▼</span>
      </div>
      <div class="tool-card-body">
        <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Arguments</div>
        <pre class="bg-slate-50 border border-slate-200 rounded p-2 text-[12px] overflow-x-auto">${escapeHtml(argsPreview)}</pre>
        ${detailBody}
      </div>
    </div>
  `;
}

function renderDetail(trace) {
  const detail = trace.result_detail || {};

  if (trace.tool_name === "rag_search") {
    const cites = detail.citations || [];
    const conf = detail.confidence || "?";
    const top = detail.top_score != null ? detail.top_score.toFixed(3) : "—";
    let html = `
      <div class="mt-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Retrieval</div>
      <div class="text-[12px] text-slate-700">Confidence: <b>${conf}</b> · top score: <code>${top}</code></div>
    `;
    if (cites.length) {
      html += `<div class="mt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Tool answer (used by agent)</div>`;
      const tcAns = detail.answer || "";
      html += `<div class="markdown text-[12.5px] text-slate-700 max-h-48 overflow-y-auto border border-slate-200 rounded p-2 bg-slate-50">
        ${renderMarkdown(tcAns)}
      </div>`;
    }
    return html;
  }

  if (trace.tool_name === "analyze_history") {
    if (detail.insufficient) {
      return `<div class="mt-3 text-amber-700 text-[12px]">⚠ Tool reported insufficient data.</div>`;
    }
    const stats = (detail.stats_summary || "").slice(0, 4000);
    return `
      <div class="mt-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Computed stats summary</div>
      <div class="markdown text-[12px] text-slate-700 max-h-80 overflow-y-auto border border-slate-200 rounded p-2 bg-slate-50">
        ${renderMarkdown(stats)}
      </div>
    `;
  }

  return "";
}

window.UI.bindToolToggles = function (rootEl) {
  rootEl.querySelectorAll("[data-tool-card]").forEach((card) => {
    const header = card.querySelector('[data-toggle="body"]');
    if (!header) return;
    header.addEventListener("click", () => card.classList.toggle("collapsed"));
  });
};

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdown(md) {
  if (!md) return "";
  const html = window.marked.parse(md);
  return window.DOMPurify.sanitize(html);
}
