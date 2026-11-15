/* Analysis page: search → table + charts, saved searches, add-to-list, reports. */
(function () {
  const cfg = window.AnalysisConfig;
  const $form = $("#searchForm");
  const charts = {};
  let table = null;
  let currentSaved = "";

  $(".s2").select2({ theme: "bootstrap-5", width: "100%", closeOnSelect: false });

  const fmtDate = (v) => v || "";
  const columns = [
    { data: null, orderable: false, render: DataTable.render.select(), width: "1rem" },
    { data: "region", title: "Region", render: (d, t, r) => (t === "display" ? App.badge(d, r.region_color) : d) },
    { data: "active_substance", title: "Active substance",
      render: (d, t, r) => (t === "display" ? `<a href="#" class="pdt-link" data-id="${r.id}">${App.esc(d)}</a>` : d) },
    { data: "brand", title: "Brand", render: (d) => App.esc(d) },
    { data: "indication", title: "Indication", render: (d, t, r) => (t === "display" ? App.badge(d, r.indication_color) : d) },
    { data: "dosage_form", title: "Dosage", render: (d, t, r) => (t === "display" ? App.badge(d, r.dosage_color) : d) },
    { data: "strength", title: "Strength", render: (d) => App.esc(d) },
    { data: "revenue_musd", title: "Revenue ($M)", className: "text-end", render: (d, t) => (t === "display" ? App.money(d) : d) },
    { data: "earliest_generic_launch", title: "Earliest generic launch", render: fmtDate },
    { data: "marketing_exclusivity", title: "ME / NCE", render: fmtDate },
    { data: "data_exclusivity", title: "DE / NCE-1", render: fmtDate },
    { data: "main_patent_expiry", title: "Main patent expiry", render: fmtDate },
    { data: "ftf_anda_filers", title: "FTF / ANDA", className: "text-end" },
    { data: "api_manufacturers", title: "API mfrs", className: "text-end" },
    { data: "api_consumption_kg", title: "API cons. (kg)", className: "text-end" },
  ];

  function renderTable(rows) {
    if (table) {
      table.clear().rows.add(rows).draw();
      return;
    }
    table = new DataTable("#resultTable", {
      data: rows, columns, order: [[8, "asc"]], pageLength: 25, scrollX: true,
      select: { style: "multi", selector: "td:first-child" },
      layout: { topStart: ["pageLength", "buttons"], topEnd: "search" },
      buttons: [{ extend: "excelHtml5", text: "Excel" }, { extend: "csvHtml5", text: "CSV" }],
    });
  }

  function chart(id, config) {
    charts[id]?.destroy();
    charts[id] = new Chart(document.getElementById(id), config);
  }

  function renderCharts(c) {
    const base = { responsive: true, plugins: { legend: { display: false } } };
    chart("chValue", { type: "bar", data: { labels: c.years, datasets: [{ data: c.value_by_year, backgroundColor: "#0d6efd" }] }, options: base });
    chart("chOffPatent", { type: "line", data: { labels: c.years, datasets: [{ data: c.off_patent_by_year, borderColor: "#20c997", tension: 0.3 }] }, options: base });
    chart("chIndications", { type: "bar", data: { labels: c.top_indications.map((x) => x[0]), datasets: [{ data: c.top_indications.map((x) => x[1]), backgroundColor: "#6f42c1" }] }, options: { ...base, indexAxis: "y" } });
    chart("chDosage", { type: "doughnut", data: { labels: c.dosage_forms.map((x) => x[0]), datasets: [{ data: c.dosage_forms.map((x) => x[1]) }] }, options: { responsive: true, plugins: { legend: { position: "bottom" } } } });
    chart("chRevApi", {
      type: "scatter", data: { datasets: [{ data: c.revenue_vs_apis, backgroundColor: "#fd7e14" }] },
      options: { ...base, scales: { x: { title: { display: true, text: "API manufacturers" } }, y: { title: { display: true, text: "Revenue ($M)" } } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.raw.label}: ${App.money(ctx.raw.y)}` } } } },
    });
  }

  function runSearch() {
    const $btn = $("#btnSearch").prop("disabled", true);
    $.post(cfg.urls.data, $form.serialize())
      .done(({ data }) => {
        const $noData = $("#noData");
        if (!data.IsRepSearchSet || !data.numproducts) {
          $("#results").addClass("d-none");
          $noData.text(data.panelmessage).removeClass("d-none");
          return;
        }
        $noData.addClass("d-none");
        $("#results").removeClass("d-none");
        $("#resultCount").text(data.numproducts + (data.truncated ? "+" : ""));
        renderTable(data.repdata);
        renderCharts(data.charts);
      })
      .fail(App.error)
      .always(() => $btn.prop("disabled", false));
  }

  $form.on("submit", (e) => { e.preventDefault(); runSearch(); });
  $("#btnReset").on("click", () => setTimeout(() => $(".s2").val(null).trigger("change"), 0));

  // ---- Saved searches ----
  function applyParams(params) {
    $form[0].reset();
    $(".s2").val(null);
    Object.entries(params).forEach(([key, value]) => {
      const $field = $form.find(`[name="${key}"]`);
      if ($field.is(":checkbox")) {
        const values = Array.isArray(value) ? value.map(String) : [value === true ? "1" : String(value)];
        $field.each(function () { this.checked = values.includes(this.value); });
      } else {
        $field.val(value);
      }
    });
    $(".s2").trigger("change");
  }

  $("#savedSearch").on("change", function () {
    currentSaved = this.value;
    $("#btnUpdateSearch, #btnDeleteSearch").prop("disabled", !currentSaved);
    if (!currentSaved) return;
    $.get(App.url(cfg.urls.savedGet, currentSaved)).done(({ data }) => { applyParams(data.params); runSearch(); }).fail(App.error);
  });

  $("#btnSaveSearch").on("click", async () => {
    const { value: name } = await Swal.fire({ title: "Save search as", input: "text", showCancelButton: true, inputValidator: (v) => !v && "Enter a name" });
    if (!name) return;
    $.post(cfg.urls.savedCreate, `${$form.serialize()}&name=${encodeURIComponent(name)}`)
      .done(({ data }) => {
        if (data.created) $("#savedSearch").append(new Option(data.name, data.id));
        $("#savedSearch").val(data.id).trigger("change");
        App.toast("Search saved");
      })
      .fail(App.error);
  });

  $("#btnUpdateSearch").on("click", () => {
    $.post(App.url(cfg.urls.savedUpdate, currentSaved), $form.serialize()).done(() => App.toast("Search updated")).fail(App.error);
  });

  $("#btnDeleteSearch").on("click", async () => {
    const ok = await Swal.fire({ title: "Delete this saved search?", icon: "warning", showCancelButton: true, confirmButtonText: "Delete" });
    if (!ok.isConfirmed) return;
    $.post(App.url(cfg.urls.savedDelete, currentSaved)).done(() => {
      $(`#savedSearch option[value="${currentSaved}"]`).remove();
      $("#savedSearch").val("").trigger("change");
      App.toast("Deleted");
    }).fail(App.error);
  });

  // ---- Add selected rows to a portfolio / play area ----
  $("#btnAddToList").on("click", () => {
    const ids = table ? table.rows({ selected: true }).data().toArray().map((r) => r.id) : [];
    if (!ids.length) return App.toast("Tick rows in the first column first", "info");
    $.post(cfg.urls.addToList, { list_id: $("#targetList").val(), "market_ids[]": ids })
      .done(({ data }) => App.toast(`${data.added} added to ${data.list}`))
      .fail(App.error);
  });

  // ---- Reports ----
  $("#btnReport").on("click", () => {
    $.post(cfg.urls.generateReport, $form.serialize())
      .done(({ task_id }) => pollReport(task_id))
      .fail(App.error);
  });

  function pollReport(taskId) {
    $.get(`/myreports/reports/status/${taskId}/`).done((s) => {
      if (s.status === "SUCCESS") window.location = s.download_url;
      else if (s.status === "FAILURE") Swal.fire({ icon: "error", title: "Report failed", text: s.error });
      else setTimeout(() => pollReport(taskId), 1500);
    }).fail(App.error);
  }

  // ---- Single product modal ----
  $("#resultTable").on("click", ".pdt-link", function (e) {
    e.preventDefault();
    $.get(App.url(cfg.urls.singleProduct, $(this).data("id"))).done(({ data }) => {
      const m = data.market;
      $("#productModalTitle").text(`${m.active_substance} — ${m.brand || ""}`);
      const props = Object.entries(data.properties).map(([k, v]) => `<tr><th>${App.esc(k)}</th><td>${App.esc(v ?? "—")}</td></tr>`).join("");
      const markets = data.markets.map((x) => `<tr><td>${App.badge(x.region, x.region_color)}</td><td>${App.money(x.revenue_musd)}</td><td>${x.earliest_generic_launch || ""}</td><td>${x.data_exclusivity || ""}</td><td>${x.main_patent_expiry || ""}</td><td>${x.api_manufacturers}</td><td>${App.esc(x.suggested_strategy)}</td></tr>`).join("");
      $("#productModalBody").html(`
        <div class="row g-3"><div class="col-lg-4"><table class="table table-sm">${props}</table></div>
        <div class="col-lg-8 table-responsive"><table class="table table-sm"><thead><tr><th>Region</th><th>Revenue</th><th>Generic launch</th><th>DE</th><th>Patent expiry</th><th>API mfrs</th><th>Strategy</th></tr></thead><tbody>${markets}</tbody></table></div></div>`);
      bootstrap.Modal.getOrCreateInstance("#productModal").show();
    }).fail(App.error);
  });

  if (cfg.autoSearch) runSearch();
})();
