/* Shared helpers: CSRF-aware AJAX, formatting, toasts. */
$.ajaxSetup({
  beforeSend(xhr, settings) {
    if (!/^(GET|HEAD|OPTIONS)$/i.test(settings.type)) xhr.setRequestHeader("X-CSRFToken", window.CSRF_TOKEN);
  },
});

window.App = {
  url(template, id) {
    // Django reversed URLs with a 0 placeholder → swap in the real id.
    return template.replace("/0/", `/${encodeURIComponent(id)}/`);
  },
  toast(title, icon = "success") {
    Swal.fire({ toast: true, position: "top-end", timer: 2200, showConfirmButton: false, icon, title });
  },
  error(xhr) {
    const msg = xhr?.responseJSON?.error || `Request failed (${xhr?.status ?? "network"})`;
    Swal.fire({ icon: "error", title: "Something went wrong", text: msg });
  },
  money(v) {
    return v == null ? "" : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 })}M`;
  },
  badge(text, color) {
    if (!text) return "";
    const span = document.createElement("span");
    span.className = "badge";
    span.style.background = color || "#6c757d";
    span.textContent = text;
    return span.outerHTML;
  },
  esc(text) {
    const d = document.createElement("div");
    d.textContent = text ?? "";
    return d.innerHTML;
  },
};
