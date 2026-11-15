/* Portfolio / Play Area table: notes, delete, copy to play area. */
(function () {
  const cfg = window.ListConfig;
  const rows = JSON.parse(document.getElementById("list-rows").textContent);
  if (!rows.length) return;

  const table = new DataTable("#listTable", {
    data: rows, pageLength: 25, scrollX: true, order: [[7, "asc"]],
    select: { style: "multi", selector: "td:first-child" },
    layout: { topStart: ["pageLength", "buttons"], topEnd: "search" },
    buttons: [{ extend: "excelHtml5", text: "Excel" }],
    columns: [
      { data: null, orderable: false, render: DataTable.render.select(), width: "1rem" },
      { data: "region", title: "Region", render: (d, t, r) => (t === "display" ? App.badge(d, r.region_color) : d) },
      { data: "active_substance", title: "Active substance", render: (d) => App.esc(d) },
      { data: "brand", title: "Brand", render: (d) => App.esc(d) },
      { data: "indication", title: "Indication", render: (d, t, r) => (t === "display" ? App.badge(d, r.indication_color) : d) },
      { data: "dosage_form", title: "Dosage", render: (d, t, r) => (t === "display" ? App.badge(d, r.dosage_color) : d) },
      { data: "revenue_musd", title: "Revenue ($M)", className: "text-end", render: (d, t) => (t === "display" ? App.money(d) : d) },
      { data: "earliest_generic_launch", title: "Earliest generic launch" },
      { data: "data_exclusivity", title: "DE / NCE-1" },
      { data: "main_patent_expiry", title: "Main patent expiry" },
      { data: "notes", title: "My notes", render: (d, t, r) => (t === "display" ? `<button class="btn btn-link btn-sm p-0 note-btn" data-id="${r.item_id}">${d ? App.esc(d) : "Add note"}</button>` : d) },
      { data: "added_by", title: "Added by" },
      { data: "added_on", title: "Added on" },
      { data: null, orderable: false, title: "", render: (d, t, r) => `<button class="btn btn-sm btn-outline-danger del-btn" data-id="${r.item_id}" aria-label="Remove"><i class="bi bi-trash"></i></button>` },
    ],
  });

  $("#listTable").on("click", ".note-btn", async function () {
    const row = table.row($(this).closest("tr"));
    const data = row.data();
    const { value, isConfirmed } = await Swal.fire({ title: "Notes", input: "textarea", inputValue: data.notes, showCancelButton: true });
    if (!isConfirmed) return;
    $.post(App.url(cfg.noteUrl, data.item_id), { notes: value }).done(() => {
      data.notes = value;
      row.data(data).draw(false);
      App.toast("Note saved");
    }).fail(App.error);
  });

  $("#listTable").on("click", ".del-btn", async function () {
    const row = table.row($(this).closest("tr"));
    const ok = await Swal.fire({ title: "Remove from this list?", icon: "warning", showCancelButton: true, confirmButtonText: "Remove" });
    if (!ok.isConfirmed) return;
    $.post(App.url(cfg.deleteUrl, row.data().item_id)).done(() => { row.remove().draw(false); App.toast("Removed"); }).fail(App.error);
  });

  $("#btnCopy").on("click", () => {
    const ids = table.rows({ selected: true }).data().toArray().map((r) => r.id);
    if (!ids.length) return App.toast("Tick rows in the first column first", "info");
    $.post(cfg.addUrl, { list_id: $("#copyTarget").val(), "market_ids[]": ids })
      .done(({ data }) => App.toast(`${data.added} copied to ${data.list}`))
      .fail(App.error);
  });
})();
