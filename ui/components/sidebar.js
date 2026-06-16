// Sidebar: user picker (radio) + conversation history list.

window.UI = window.UI || {};

const USER_OPTIONS = [
  { id: "user_a", label: "Alex (user_a)", note: "Consistent PPL, 64 entries" },
  { id: "user_b", label: "Binh (user_b)", note: "Chest-dominant, 28 entries" },
  { id: "anonymous", label: "No history", note: "Knowledge-only mode" },
];

window.UI.renderUserPicker = function (containerEl, currentUserId, onChange) {
  containerEl.innerHTML = USER_OPTIONS.map(
    (u) => `
    <label class="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-slate-50 cursor-pointer">
      <input type="radio" name="user-picker" value="${u.id}" ${u.id === currentUserId ? "checked" : ""} class="mt-1" />
      <div class="flex-1 min-w-0">
        <div class="text-sm font-medium text-slate-800">${u.label}</div>
        <div class="text-[11px] text-slate-500">${u.note}</div>
      </div>
    </label>
  `,
  ).join("");

  containerEl.querySelectorAll("input[name='user-picker']").forEach((input) => {
    input.addEventListener("change", (e) => onChange(e.target.value));
  });
};

window.UI.renderConversationList = function (
  containerEl,
  conversations,
  currentId,
  callbacks,
) {
  if (conversations.length === 0) {
    containerEl.innerHTML = `<p class="text-xs text-slate-400 px-2 py-2">No conversations yet</p>`;
    return;
  }

  containerEl.innerHTML = conversations
    .slice()
    .reverse()
    .map(
      (c) => `
    <div class="group flex items-center gap-1 px-2 py-1.5 rounded hover:bg-slate-100 ${
      c.id === currentId ? "bg-brand-500/10" : ""
    }">
      <button data-load-id="${c.id}" class="flex-1 text-left text-sm text-slate-800 truncate min-w-0">
        ${escapeHtml(c.title || "(untitled)")}
      </button>
      <button
        data-delete-id="${c.id}"
        class="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 text-xs px-1"
        title="Delete"
      >
        ×
      </button>
    </div>
  `,
    )
    .join("");

  containerEl.querySelectorAll("[data-load-id]").forEach((btn) => {
    btn.addEventListener("click", () => callbacks.onLoad(btn.dataset.loadId));
  });
  containerEl.querySelectorAll("[data-delete-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      callbacks.onDelete(btn.dataset.deleteId);
    });
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
