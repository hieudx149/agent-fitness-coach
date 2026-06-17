// Renders a list of RAG source citations as collapsible cards.
// Each citation is {index, source_file, section_title, score, snippet, chunk_id}.

window.UI = window.UI || {};

window.UI.renderCitations = function (sources) {
  if (!sources || sources.length === 0) return "";

  const cards = sources
    .map(
      (src) => `
    <div class="citation-card">
      <div class="flex justify-between items-center cursor-pointer" data-toggle="snippet">
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-[11px] font-mono text-brand-700 shrink-0">[${src.index}]</span>
          <span class="font-medium text-slate-800 truncate">${escapeHtml(src.source_file)}</span>
          <span class="text-slate-500 truncate">— ${escapeHtml(src.section_title || "")}</span>
        </div>
        <span class="text-[11px] font-mono text-slate-500 ml-2 shrink-0">${(src.score ?? 0).toFixed(3)}</span>
      </div>
      <div class="snippet hidden mt-2 text-slate-600 text-[12px] border-t border-blue-100 pt-2">
        ${escapeHtml(src.snippet || "")}
      </div>
    </div>
  `,
    )
    .join("");

  return `
    <div class="mt-3 space-y-1.5">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Sources (${sources.length})
      </div>
      ${cards}
    </div>
  `;
};

// Renders workout-data references — the [Dn] facts from analyze_history the
// answer cited. Mirrors the source cards but for computed personal stats.
// Each data point is {ref, category, label, detail}.
window.UI.renderDataPoints = function (dataPoints) {
  if (!dataPoints || dataPoints.length === 0) return "";

  const cards = dataPoints
    .map(
      (dp) => `
    <div class="citation-card">
      <div class="flex justify-between items-center gap-2">
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-[11px] font-mono text-brand-700 shrink-0">[${escapeHtml(dp.ref)}]</span>
          <span class="font-medium text-slate-800 truncate">${escapeHtml(dp.label)}</span>
        </div>
        <span class="text-[11px] font-medium text-slate-500 ml-2 shrink-0">${escapeHtml(dp.category || "")}</span>
      </div>
      <div class="mt-1.5 text-slate-600 text-[12px]">${escapeHtml(dp.detail || "")}</div>
    </div>
  `,
    )
    .join("");

  return `
    <div class="mt-3 space-y-1.5">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Workout data (${dataPoints.length})
      </div>
      ${cards}
    </div>
  `;
};

// Hook up click-to-expand AFTER the HTML has been inserted into the DOM.
window.UI.bindCitationToggles = function (rootEl) {
  rootEl.querySelectorAll(".citation-card").forEach((card) => {
    const header = card.querySelector('[data-toggle="snippet"]');
    const snippet = card.querySelector(".snippet");
    if (!header || !snippet) return;
    header.addEventListener("click", () => snippet.classList.toggle("hidden"));
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
