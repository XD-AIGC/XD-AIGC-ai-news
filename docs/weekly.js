/* weekly.js — client-side renderer for the weekly digest page */
(function () {
  "use strict";

  // ── Theme ──
  var savedTheme = localStorage.getItem("theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);

  var themeBtn = document.getElementById("themeToggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
    });
  }

  // ── DOM references ──
  const dom = {
    loading: document.getElementById("loadingState"),
    error: document.getElementById("errorState"),
    errorMsg: document.getElementById("errorMessage"),
    content: document.getElementById("weeklyContent"),
    prevWeek: document.getElementById("prevWeek"),
    nextWeek: document.getElementById("nextWeek"),
    weekLabel: document.getElementById("weekLabel"),
    bannerTitle: document.getElementById("bannerTitle"),
    bannerDateRange: document.getElementById("bannerDateRange"),
    bannerCount: document.getElementById("bannerCount"),
    bannerTags: document.getElementById("bannerTags"),
    top10List: document.getElementById("top10List"),
    statsGrid: document.getElementById("statsGrid"),
    editorNote: document.getElementById("editorNote"),
    story3Quotes: document.getElementById("story3Quotes"),
    story3Doraemon: document.getElementById("story3Doraemon"),
  };

  // ── State ──
  var weekIndex = [];   // array from index.json
  var currentIdx = -1;  // pointer into weekIndex

  // ── Helpers ──

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function clearChildren(parent) {
    while (parent.firstChild) parent.removeChild(parent.firstChild);
  }

  /** Extract short week label like "W11" from "2026-W11". */
  function shortWeek(weekStr) {
    var m = weekStr.match(/W(\d+)/);
    return m ? "W" + m[1] : weekStr;
  }

  // ── Data fetching ──

  function fetchJSON(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status + " for " + url);
      return res.json();
    });
  }

  // ── Rendering ──

  function showError(msg) {
    hide(dom.loading);
    hide(dom.content);
    dom.errorMsg.textContent = msg;
    show(dom.error);
  }

  function showContent() {
    hide(dom.loading);
    hide(dom.error);
    show(dom.content);
  }

  function updateNavButtons() {
    dom.prevWeek.disabled = currentIdx >= weekIndex.length - 1;
    dom.nextWeek.disabled = currentIdx <= 0;
    if (currentIdx >= 0 && currentIdx < weekIndex.length) {
      dom.weekLabel.textContent = shortWeek(weekIndex[currentIdx].week);
    }
  }

  function renderBanner(data) {
    dom.bannerTitle.textContent = data.week_title || "";
    dom.bannerDateRange.textContent = data.date_range || "";

    var sourceCount = data.total_sources || 0;
    var newsCount = data.total_news || 0;
    dom.bannerCount.textContent =
      "\u5171 " + newsCount + " \u6761\u65B0\u95FB \u00B7 " +
      sourceCount + " \u4E2A\u6765\u6E90";

    clearChildren(dom.bannerTags);
    if (data.stats && data.stats.by_category) {
      Object.keys(data.stats.by_category).forEach(function (cat) {
        dom.bannerTags.appendChild(el("span", "tag-pill", cat));
      });
    }
  }

  function renderStory(index, story, weekStr) {
    var n = index + 1; // 1-based
    var prefix = "story" + n;

    // Label, title, summary
    var labelEl = document.getElementById(prefix + "Label");
    var titleEl = document.getElementById(prefix + "Title");
    var summaryEl = document.getElementById(prefix + "Summary");
    if (labelEl) labelEl.textContent = story.label || "";
    if (titleEl) titleEl.textContent = story.title || "";
    if (summaryEl) summaryEl.textContent = story.summary || "";

    // Panels (images)
    var panelsContainer = document.getElementById(prefix + "Panels");
    if (panelsContainer) {
      var panels = panelsContainer.querySelectorAll(".comic-panel");
      var images = story.panels_images || [];
      panels.forEach(function (panel, i) {
        clearChildren(panel);
        if (images[i]) {
          var img = document.createElement("img");
          img.src = "data/weekly/" + weekStr + "/" + images[i];
          img.alt = "Panel " + (i + 1);
          img.onerror = function () {
            clearChildren(panel);
            panel.appendChild(
              el("div", "comic-panel-placeholder", "Panel " + (i + 1))
            );
          };
          panel.appendChild(img);
        } else {
          panel.appendChild(
            el("div", "comic-panel-placeholder", "Panel " + (i + 1))
          );
        }
      });
    }

    // Highlights
    var highlightsEl = document.getElementById(prefix + "Highlights");
    if (highlightsEl) {
      clearChildren(highlightsEl);
      (story.highlights || []).forEach(function (h) {
        highlightsEl.appendChild(el("li", null, h));
      });
    }

    // Related news
    var relatedEl = document.getElementById(prefix + "Related");
    if (relatedEl) {
      // Keep the title, remove old related-items
      var oldItems = relatedEl.querySelectorAll(".related-item");
      oldItems.forEach(function (item) { item.remove(); });

      (story.related_news || []).forEach(function (r) {
        var row = el("div", "related-item");
        row.appendChild(el("span", "related-score", String(r.score)));
        if (r.url) {
          var link = document.createElement("a");
          link.href = r.url;
          link.target = "_blank";
          link.rel = "noopener";
          link.className = "related-link";
          link.textContent = r.title;
          row.appendChild(link);
        } else {
          row.appendChild(el("span", "related-link", r.title));
        }
        relatedEl.appendChild(row);
      });
    }

    // Story 3 special: community quotes + doraemon
    if (n === 3) {
      if (story.community_quotes && story.community_quotes.length > 0) {
        clearChildren(dom.story3Quotes);
        story.community_quotes.forEach(function (q) {
          var line = el("div", null);
          line.innerHTML =
            "\u201C" + escapeHtml(q.text) + "\u201D" +
            (q.author ? " \u2014 " + escapeHtml(q.author) : "");
          dom.story3Quotes.appendChild(line);
        });
        show(dom.story3Quotes);
      } else {
        hide(dom.story3Quotes);
      }

      if (story.doraemon_quote) {
        dom.story3Doraemon.textContent = story.doraemon_quote;
        show(dom.story3Doraemon);
      } else {
        hide(dom.story3Doraemon);
      }
    }
  }

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function renderTop10(list) {
    clearChildren(dom.top10List);
    (list || []).forEach(function (item) {
      var li = el("li", "top10-item");

      var rank = el("span", "top10-rank", String(item.rank));
      if (item.rank <= 3) rank.classList.add("top3");
      li.appendChild(rank);

      li.appendChild(el("span", "top10-score", String(item.score)));
      if (item.url) {
        var link = document.createElement("a");
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.className = "top10-title";
        link.textContent = item.title;
        li.appendChild(link);
      } else {
        li.appendChild(el("span", "top10-title", item.title));
      }
      dom.top10List.appendChild(li);
    });
  }

  function renderStats(data) {
    clearChildren(dom.statsGrid);

    // Total news
    var totalBlock = document.createElement("div");
    totalBlock.appendChild(el("div", "stat-block-title", "TOTAL NEWS"));
    totalBlock.appendChild(el("div", "stat-number", String(data.total_news || 0)));
    dom.statsGrid.appendChild(totalBlock);

    // By category
    if (data.stats && data.stats.by_category) {
      var catBlock = document.createElement("div");
      catBlock.appendChild(el("div", "stat-block-title", "BY CATEGORY"));
      Object.keys(data.stats.by_category).forEach(function (key) {
        var row = el("div", "stat-row");
        row.appendChild(el("span", null, key));
        row.appendChild(
          el("span", "stat-row-value", String(data.stats.by_category[key]))
        );
        catBlock.appendChild(row);
      });
      dom.statsGrid.appendChild(catBlock);
    }

    // By source
    if (data.stats && data.stats.by_source) {
      var srcBlock = document.createElement("div");
      srcBlock.appendChild(el("div", "stat-block-title", "BY SOURCE"));
      Object.keys(data.stats.by_source).forEach(function (key) {
        var row = el("div", "stat-row");
        row.appendChild(el("span", null, key));
        row.appendChild(
          el("span", "stat-row-value", String(data.stats.by_source[key]))
        );
        srcBlock.appendChild(row);
      });
      dom.statsGrid.appendChild(srcBlock);
    }
  }

  function renderDigest(data) {
    renderBanner(data);

    var stories = data.stories || [];
    for (var i = 0; i < 3; i++) {
      if (stories[i]) {
        renderStory(i, stories[i], data.week);
      }
    }

    renderTop10(data.top10);
    renderStats(data);

    dom.editorNote.textContent = data.editor_note || "";
    showContent();
  }

  // ── Navigation ──

  function loadWeek(idx) {
    if (idx < 0 || idx >= weekIndex.length) return;
    currentIdx = idx;
    updateNavButtons();

    var week = weekIndex[idx].week;
    window.location.hash = week;

    hide(dom.content);
    hide(dom.error);
    show(dom.loading);

    fetchJSON("data/weekly/" + week + "/digest.json")
      .then(renderDigest)
      .catch(function (err) {
        showError("Failed to load digest: " + err.message);
      });
  }

  function findWeekIdx(weekStr) {
    for (var i = 0; i < weekIndex.length; i++) {
      if (weekIndex[i].week === weekStr) return i;
    }
    return -1;
  }

  // ── Events ──

  // index.json is sorted newest-first, so prev (←) = older = higher index
  dom.prevWeek.addEventListener("click", function () {
    if (currentIdx < weekIndex.length - 1) loadWeek(currentIdx + 1);
  });

  dom.nextWeek.addEventListener("click", function () {
    if (currentIdx > 0) loadWeek(currentIdx - 1);
  });

  window.addEventListener("hashchange", function () {
    var hash = window.location.hash.replace(/^#/, "");
    if (hash) {
      var idx = findWeekIdx(hash);
      if (idx >= 0 && idx !== currentIdx) loadWeek(idx);
    }
  });

  // ── Init ──

  fetchJSON("data/weekly/index.json")
    .then(function (index) {
      weekIndex = index;
      if (weekIndex.length === 0) {
        showError("No weekly digests available.");
        return;
      }

      // Check URL hash first
      var hash = window.location.hash.replace(/^#/, "");
      var startIdx = -1;
      if (hash) startIdx = findWeekIdx(hash);

      // Default to latest (first element — index.json is sorted newest-first)
      if (startIdx < 0) startIdx = 0;

      loadWeek(startIdx);
    })
    .catch(function (err) {
      showError("Failed to load weekly index: " + err.message);
    });
})();
