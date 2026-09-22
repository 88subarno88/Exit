/* Shared behaviour for every surface. No dependencies beyond Chart.js.
   - theme switch (light / dark / follow the system), remembered per browser
   - a chart registry so charts are redrawn in the new theme's colours
   - "/" focuses search; table filter, sort and grade toggles on the big tables
   All of it is progressive: the pages still read fine with JS off. */
(function () {
  "use strict";

  var EXIT = (window.EXIT = window.EXIT || {});

  // --- theme --------------------------------------------------------------
  var KEY = "exit-theme";                     // "light" | "dark" | absent = system

  function current() {
    var set = document.documentElement.getAttribute("data-theme");
    if (set) return set;
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function apply(theme) {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    else document.documentElement.removeAttribute("data-theme");
    EXIT.redraw();
  }

  EXIT.toggleTheme = function () {
    var next = current() === "dark" ? "light" : "dark";
    try { localStorage.setItem(KEY, next); } catch (e) { /* private mode */ }
    apply(next);
  };

  // follow the OS while the reader has not chosen for themselves
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
    var stored = null;
    try { stored = localStorage.getItem(KEY); } catch (e) { /* ignore */ }
    if (!stored) EXIT.redraw();
  });

  // --- chart registry -----------------------------------------------------
  // A page calls EXIT.chart(fn); fn draws and returns its Chart instance(s).
  // On a theme change every chart is destroyed and drawn again, so the colours
  // it read out of the stylesheet are the colours now in force.
  var drawers = [], live = [];

  EXIT.css = function (name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  };

  EXIT.chartDefaults = function () {
    if (!window.Chart) return;
    Chart.defaults.font.family = EXIT.css("--font") ||
      'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = EXIT.css("--muted");
    Chart.defaults.borderColor = EXIT.css("--grid");
    Chart.defaults.animation = false;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.plugins.tooltip.backgroundColor = EXIT.css("--ink");
    Chart.defaults.plugins.tooltip.titleColor = EXIT.css("--bg");
    Chart.defaults.plugins.tooltip.bodyColor = EXIT.css("--bg");
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.displayColors = false;
    Chart.defaults.plugins.tooltip.titleFont = { weight: "600" };
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.legend.labels.padding = 14;
    Chart.defaults.scale.grid.color = EXIT.css("--grid");
    Chart.defaults.scale.border = Chart.defaults.scale.border || {};
    Chart.defaults.scale.border.color = EXIT.css("--line");
    Chart.defaults.scale.ticks.padding = 6;
    Chart.defaults.scale.ticks.maxRotation = 0;   // slanted money labels read badly
  };

  EXIT.chart = function (draw) {
    drawers.push(draw);
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () { run(draw); });
    } else {
      run(draw);
    }
  };

  function run(draw) {
    EXIT.chartDefaults();
    var made = draw();
    if (made) live = live.concat(made);
  }

  EXIT.redraw = function () {
    live.forEach(function (c) { try { c.destroy(); } catch (e) { /* already gone */ } });
    live = [];
    drawers.forEach(run);
  };

  // --- shared number formatting for charts --------------------------------
  EXIT.usd = function (v) {
    v = +v;
    if (!isFinite(v)) return "—";
    var a = Math.abs(v);
    if (a >= 1e12) return "$" + (v / 1e12).toPrecision(3) + "T";
    if (a >= 1e9) return "$" + (v / 1e9).toPrecision(3) + "B";
    if (a >= 1e6) return "$" + (v / 1e6).toPrecision(3) + "M";
    if (a >= 1e3) return "$" + (v / 1e3).toPrecision(3) + "k";
    return "$" + (a >= 1 ? Math.round(v) : v.toPrecision(3));
  };

  EXIT.pct = function (bps) {
    return bps >= 100 ? (bps / 100).toFixed(1) + "%" : (+bps).toFixed(1) + " bps";
  };

  // --- page wiring --------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("theme-toggle");
    if (toggle) toggle.addEventListener("click", EXIT.toggleTheme);

    // "/" jumps to search, Escape leaves it
    var search = document.querySelector("header.site form.search input");
    document.addEventListener("keydown", function (e) {
      var tag = (e.target.tagName || "").toLowerCase();
      var typing = tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable;
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && search) {
        e.preventDefault();
        search.focus();
        search.select();
      } else if (e.key === "Escape" && e.target === search) {
        search.blur();
      }
    });

    wireTables();
  });

  // --- filterable, sortable tables ---------------------------------------
  function rowsOf(table) {
    return Array.prototype.slice.call(table.tBodies[0] ? table.tBodies[0].rows : []);
  }

  function visible(table, count) {
    if (!count) return;
    var n = rowsOf(table).filter(function (r) { return !r.hidden; }).length;
    count.textContent = n + " of " + rowsOf(table).length + " " + (count.dataset.noun || "rows");
  }

  function wireTables() {
    document.querySelectorAll("table[data-enhance]").forEach(function (table) {
      var tools = document.querySelector('[data-tools-for="' + table.id + '"]');
      var input = tools && tools.querySelector("input[type=search]");
      var count = tools && tools.querySelector(".count");
      var grades = tools ? Array.prototype.slice.call(tools.querySelectorAll(".gfilter")) : [];

      function refilter() {
        var term = (input && input.value || "").trim().toLowerCase();
        var on = grades.filter(function (b) { return b.getAttribute("aria-pressed") === "true"; })
                       .map(function (b) { return b.dataset.grade; });
        var all = grades.length === 0 || on.length === grades.length || on.length === 0;
        rowsOf(table).forEach(function (row) {
          var byText = !term || (row.dataset.search || row.textContent).toLowerCase().indexOf(term) !== -1;
          var byGrade = all || on.indexOf(row.dataset.grade) !== -1;
          row.hidden = !(byText && byGrade);
        });
        visible(table, count);
      }

      if (input) {
        input.addEventListener("input", refilter);
        input.addEventListener("search", refilter);
      }
      if (tools) {
        tools.querySelectorAll("[data-filter-reset]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            if (input) input.value = "";
            grades.forEach(function (b) { b.setAttribute("aria-pressed", "true"); });
            refilter();
          });
        });
      }
      grades.forEach(function (btn) {
        btn.addEventListener("click", function () {
          var pressed = btn.getAttribute("aria-pressed") === "true";
          // first click on a chip while everything is on isolates that grade
          var allOn = grades.every(function (b) { return b.getAttribute("aria-pressed") === "true"; });
          if (allOn) {
            grades.forEach(function (b) { b.setAttribute("aria-pressed", String(b === btn)); });
          } else {
            btn.setAttribute("aria-pressed", String(!pressed));
            if (grades.every(function (b) { return b.getAttribute("aria-pressed") === "false"; })) {
              grades.forEach(function (b) { b.setAttribute("aria-pressed", "true"); });
            }
          }
          refilter();
        });
      });

      // click a header to sort; data-v on a cell carries the raw value
      table.querySelectorAll("th[data-sort]").forEach(function (th) {
        th.setAttribute("tabindex", "0");
        th.setAttribute("role", "button");
        var sortIt = function () {
          var idx = Array.prototype.indexOf.call(th.parentNode.cells, th);
          var desc = th.getAttribute("aria-sort") !== "descending";
          table.querySelectorAll("th[data-sort]").forEach(function (o) { o.removeAttribute("aria-sort"); });
          th.setAttribute("aria-sort", desc ? "descending" : "ascending");
          var body = table.tBodies[0];
          rowsOf(table).map(function (row) {
            var cell = row.cells[idx];
            var raw = cell && cell.dataset.v !== undefined ? cell.dataset.v : (cell ? cell.textContent : "");
            var num = parseFloat(raw);
            return { row: row, n: isNaN(num) ? null : num, s: String(raw).trim().toLowerCase() };
          }).sort(function (a, b) {
            if (a.n !== null && b.n !== null) return desc ? b.n - a.n : a.n - b.n;
            if (a.n !== null) return -1;
            if (b.n !== null) return 1;
            return desc ? b.s.localeCompare(a.s) : a.s.localeCompare(b.s);
          }).forEach(function (o) { body.appendChild(o.row); });
        };
        th.addEventListener("click", sortIt);
        th.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortIt(); }
        });
      });

      visible(table, count);
    });
  }
})();
