// Sidebar: role picker (coach / gymer) + dependent target picker (client list
// for coach, gymer roster for gymer) + conversation history list.

window.UI = window.UI || {};

const ROLES = [
  { id: "coach", label: "🧑‍🏫 Coach", note: "Manage a client roster" },
  { id: "gymer", label: "🏋️ Gymer", note: "Self-coaching mode" },
];

window.UI.renderRolePicker = function (containerEl, currentRole, onChange) {
  containerEl.innerHTML = ROLES.map(
    (r) => `
    <label class="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-slate-50 cursor-pointer">
      <input type="radio" name="role-picker" value="${r.id}" ${r.id === currentRole ? "checked" : ""} class="mt-1" />
      <div class="flex-1 min-w-0">
        <div class="text-sm font-medium text-slate-800">${r.label}</div>
        <div class="text-[11px] text-slate-500">${r.note}</div>
      </div>
    </label>
  `,
  ).join("");

  containerEl.querySelectorAll("input[name='role-picker']").forEach((input) => {
    input.addEventListener("change", (e) => onChange(e.target.value));
  });
};

window.UI.renderTargetPicker = function (containerEl, role, targets, currentTargetId, onChange) {
  if (!targets || targets.length === 0) {
    containerEl.innerHTML = `<p class="text-xs text-slate-400 px-2 py-2">No targets available</p>`;
    return;
  }

  const heading =
    role === "coach"
      ? "Talking about client"
      : "Gymer profile";

  containerEl.innerHTML = `
    <h2 class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
      ${heading}
    </h2>
    <div class="space-y-1">
      ${targets
        .map(
          (t) => `
        <label class="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-slate-50 cursor-pointer">
          <input type="radio" name="target-picker" value="${t.id}" ${t.id === currentTargetId ? "checked" : ""} class="mt-1" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-slate-800">${escapeHtml(t.name)}</div>
            <div class="text-[11px] text-slate-500">
              ${t.n_workouts > 0 ? `${t.n_workouts} workouts` : "no history"}
            </div>
          </div>
        </label>
      `,
        )
        .join("")}
    </div>
  `;

  containerEl.querySelectorAll("input[name='target-picker']").forEach((input) => {
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
