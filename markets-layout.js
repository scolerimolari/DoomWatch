
/* DOOMWATCH MARKETS — COMPACT NAVIGATION
   Works with the existing markets.html.
   Does not alter collector data or existing chart functions.
*/
(() => {
  "use strict";

  function initialise() {
    const main = document.querySelector("main");
    if (!main || main.dataset.compactReady) return;

    main.dataset.compactReady = "yes";

    const headings = [...main.querySelectorAll(":scope > h2")];
    if (!headings.length) return;

    const terminal = main.querySelector(":scope > .terminal");

    const style = document.createElement("style");
    style.textContent = `
      .dw-nav {
        position: sticky;
        top: 0;
        z-index: 50;
        display: flex;
        gap: 6px;
        overflow-x: auto;
        padding: 9px;
        margin: 12px -9px;
        background: #171b14;
        border-top: 1px solid #414738;
        border-bottom: 2px solid #626b38;
        scrollbar-width: thin;
      }
      .dw-nav button {
        flex: 0 0 auto;
        padding: 10px 12px;
        border: 1px solid #414738;
        background: #24291f;
        color: #b69a69;
        font: inherit;
        font-size: 11px;
        letter-spacing: 1px;
        cursor: pointer;
      }
      .dw-nav button.active {
        background: #626b38;
        border-color: #f0c83e;
        color: #fff;
      }
      .dw-view { display: none; }
      .dw-view.active { display: block; }
      .dw-view > .dw-section:first-child h2 { margin-top: 15px; }
      .dw-overview {
        display: grid;
        grid-template-columns: repeat(auto-fit,minmax(145px,1fr));
        gap: 9px;
        margin: 12px 0;
      }
      .dw-jump {
        display: block;
        width: 100%;
        min-height: 76px;
        padding: 12px;
        text-align: left;
        background: #1b1f19;
        color: #e8e8d9;
        border: 1px solid #414738;
        border-left: 3px solid #626b38;
        font: inherit;
        cursor: pointer;
      }
      .dw-jump strong {
        display: block;
        color: #f0c83e;
        font-size: 11px;
        margin-bottom: 7px;
      }
      .dw-jump span {
        color: #999e8e;
        font-size: 10px;
        line-height: 1.4;
      }
      .dw-overview-title {
        color: #f0c83e;
        font-size: 12px;
        letter-spacing: 2px;
        margin: 18px 0 8px;
      }
      details.dw-expand {
        margin: 10px 0;
        border: 1px solid #414738;
        background: #171b14;
      }
      details.dw-expand > summary {
        padding: 12px;
        color: #f0c83e;
        cursor: pointer;
        font-size: 11px;
        letter-spacing: 1px;
        list-style: none;
      }
      details.dw-expand > summary::-webkit-details-marker {
        display: none;
      }
      details.dw-expand > summary:after {
        content: "+";
        float: right;
        color: #ff9b37;
        font-size: 16px;
      }
      details.dw-expand[open] > summary:after {
        content: "−";
      }
      details.dw-expand > .panel {
        border: 0;
        border-top: 1px solid #414738;
      }
      .dw-search {
        width: 100%;
        max-width: 420px;
        margin: 8px 0 12px;
        padding: 11px;
        background: #11150f;
        color: #7dff86;
        border: 1px solid #626b38;
        font: inherit;
      }
      @media(max-width:600px) {
        .dw-nav { margin-left: -9px; margin-right: -9px; }
        .dw-nav button { padding: 11px 13px; }
      }
    `;
    document.head.appendChild(style);

    const tabs = [
      ["overview", "OVERVIEW"],
      ["markets", "MARKETS"],
      ["commodities", "COMMODITIES"],
      ["currency", "CURRENCY"],
      ["essentials", "ESSENTIALS"],
      ["energy", "ENERGY"],
      ["news", "NEWS & RISK"],
      ["sources", "SOURCES"]
    ];

    const groups = {};
    tabs.forEach(([id]) => {
      groups[id] = [];
    });

    function destination(heading) {
      const t = heading.textContent.toLowerCase();

      if (t.includes("global financial") ||
          t.includes("top 10 stocks")) return "markets";

      if (t.includes("commodit") ||
          t.includes("agricultural")) return "commodities";

      if (t.includes("digital assets") ||
          t.includes("currency")) return "currency";

      if (t.includes("household essentials")) return "essentials";

      if (t.includes("heating oil") ||
          t.includes("petrol") ||
          t.includes("diesel")) return "energy";

      if (t.includes("financial") ||
          t.includes("supply-chain")) return "news";

      if (t.includes("data sources")) return "sources";

      return "markets";
    }

    const views = {};
    tabs.forEach(([id]) => {
      const view = document.createElement("div");
      view.className = "dw-view";
      view.dataset.view = id;
      views[id] = view;
    });

    headings.forEach(heading => {
      const section = document.createElement("section");
      section.className = "dw-section";

      let node = heading;
      while (node && node !== main) {
        const next = node.nextElementSibling;
        if (next && next.tagName === "H2") break;

        section.appendChild(node);
        node = next;
      }

      groups[destination(heading)].push(section);
    });

    const nav = document.createElement("div");
    nav.className = "dw-nav";
    nav.setAttribute("aria-label", "Markets navigation");

    const overview = views.overview;
    const overviewTitle = document.createElement("div");
    overviewTitle.className = "dw-overview-title";
    overviewTitle.textContent = "QUICK ACCESS // SELECT AN OPERATIONAL AREA";
    overview.appendChild(overviewTitle);

    const quick = document.createElement("div");
    quick.className = "dw-overview";

    const descriptions = {
      markets: ["GLOBAL MARKETS", "Indices, market history and the top ten stocks"],
      commodities: ["COMMODITIES", "Gold, silver, Brent and agricultural prices"],
      currency: ["CURRENCY & DIGITAL", "Exchange rates and Bitcoin"],
      essentials: ["HOUSEHOLD ESSENTIALS", "Food inflation, grocery prices and basket trends"],
      energy: ["HOUSEHOLD ENERGY", "NI heating oil, petrol and diesel"],
      news: ["NEWS & RISK", "Financial news and supply-chain pressure"],
      sources: ["DATA SOURCES", "Origins, update frequency and data quality"]
    };

    Object.entries(descriptions).forEach(([id, info]) => {
      const button = document.createElement("button");
      button.className = "dw-jump";
      button.innerHTML =
        `<strong>${info[0]}</strong><span>${info[1]}</span>`;
      button.addEventListener("click", () => showView(id));
      quick.appendChild(button);
    });

    overview.appendChild(quick);

    const overviewNote = document.createElement("div");
    overviewNote.className = "terminal";
    overviewNote.innerHTML =
      "DOOMWATCH // MARKETS OVERVIEW<br>" +
      "SELECT A SECTION TO OPEN ITS DATA AND CHARTS.<br>" +
      "ORIGINAL COLLECTOR AND DATA SOURCES RETAINED.";
    overview.appendChild(overviewNote);

    Object.entries(groups).forEach(([id, sections]) => {
      sections.forEach(section => views[id].appendChild(section));
    });

    tabs.forEach(([id, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.dataset.target = id;
      button.addEventListener("click", () => showView(id));
      nav.appendChild(button);
    });

    if (terminal) {
      terminal.insertAdjacentElement("afterend", nav);
      nav.insertAdjacentElement("afterend", overview);
    } else {
      main.prepend(nav, overview);
    }

    Object.entries(views).forEach(([id, view]) => {
      if (id !== "overview") {
        view.style.display = "none";
      }
      nav.insertAdjacentElement("afterend", view);
    });

    function showView(id) {
      if (!views[id]) return;

      overview.style.display = id === "overview" ? "block" : "none";

      Object.entries(views).forEach(([key, view]) => {
        view.classList.toggle("active", key === id);
        view.style.display = key === id ? "block" : "none";
      });

      nav.querySelectorAll("button").forEach(button => {
        const active = button.dataset.target === id;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", String(active));
      });

      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    /* Make the long charts expandable without changing their contents. */
    main.querySelectorAll(".chart-panel").forEach(panel => {
      if (panel.closest("details")) return;

      const title = panel.querySelector(".panel-title");
      const label = title ? title.textContent.trim() : "CHART DETAILS";

      const details = document.createElement("details");
      details.className = "dw-expand";

      const summary = document.createElement("summary");
      summary.textContent = "OPEN CHART // " + label;

      panel.parentNode.insertBefore(details, panel);
      details.append(summary, panel);
    });

    /* Add simple filters to the existing stock and grocery tables. */
    function addTableSearch(tableId, placeholder) {
      const table = document.getElementById(tableId);
      if (!table) return;

      const wrapper = table.closest(".panel");
      if (!wrapper || wrapper.querySelector(".dw-search")) return;

      const input = document.createElement("input");
      input.type = "search";
      input.className = "dw-search";
      input.placeholder = placeholder;
      input.setAttribute("aria-label", placeholder);

      input.addEventListener("input", () => {
        const query = input.value.toLowerCase();
        table.querySelectorAll("tbody tr").forEach(row => {
          row.hidden = !row.textContent.toLowerCase().includes(query);
        });
      });

      wrapper.insertBefore(input, table);
    }

    addTableSearch("stock-rows", "Search companies or ticker symbols...");
    addTableSearch("basket-rows", "Search grocery items or retailers...");

    showView("overview");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialise);
  } else {
    initialise();
  }
})();
