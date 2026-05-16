/**
 * archive-loader.js — The Daily Llama
 *
 * Loads monthly archive JSON files from ../archive/ and renders them
 * grouped by year/month with toggleable month sections.
 * Pure vanilla JS.
 */

(function () {
  'use strict';

  const ARCHIVE_LIST_URL = '../archive/index.json';
  const ARCHIVE_DIR     = '../archive/';
  const container       = document.getElementById('archive-container');
  const loadingEl       = document.getElementById('archive-loading');
  const errorEl         = document.getElementById('archive-error');

  async function main() {
    if (!container) return;

    try {
      // Fetch index
      const resp = await fetch(ARCHIVE_LIST_URL);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
      const months = await resp.json();  // e.g. ["2026-05", "2026-04", ...]

      if (!months.length) {
        container.innerHTML = '<p class="text-center" style="color:var(--text-muted);padding:40px 0;">No archived feeds yet.</p>';
        if (loadingEl) loadingEl.classList.add('hidden');
        return;
      }

      // Load each month file
      const yearGroups = {};
      for (const monthSlug of months.slice(0, 12)) {
        try {
          const mResp = await fetch(ARCHIVE_DIR + monthSlug + '.json');
          if (!mResp.ok) continue;
          const data = await mResp.json();

          const [year, month] = monthSlug.split('-');
          if (!yearGroups[year]) yearGroups[year] = [];
          yearGroups[year].push({
            slug: monthSlug,
            label: new Date(parseInt(year), parseInt(month) - 1).toLocaleString('en-US', { month: 'long', year: 'numeric' }),
            articles: data.news_cards || [],
            featured: data.featured_video || null,
            runner_ups: data.runner_ups || [],
          });
        } catch (_) {
          // Skip months that fail to load
        }
      }

      render(yearGroups);
    } catch (err) {
      if (errorEl) {
        errorEl.classList.remove('hidden');
        errorEl.textContent = 'Failed to load archive: ' + err.message;
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('hidden');
    }
  }

  function render(yearGroups) {
    const years = Object.keys(yearGroups).sort().reverse();
    let html = '';

    for (const year of years) {
      html += `<div class="archive-year"><h2>${year}</h2>`;
      for (const month of yearGroups[year]) {
        const total = month.articles.length + (month.featured ? 1 : 0) + month.runner_ups.length;
        html += `
          <div class="archive-month">
            <h3 onclick="this.nextElementSibling.classList.toggle('hidden')">
              ${esc(month.label)} — ${total} article${total !== 1 ? 's' : ''}
            </h3>
            <div class="archive-articles hidden">
              ${month.featured ? renderFeaturedRow(month.featured) : ''}
              ${month.runner_ups.map(ru => renderArticleRow(ru, 'Runner-up')).join('')}
              ${month.articles.map(a => renderArticleRow(a, '')).join('')}
            </div>
          </div>
        `;
      }
      html += '</div>';
    }

    container.innerHTML = html || '<p class="text-center" style="color:var(--text-muted);padding:40px 0;">No archives to display.</p>';
  }

  function renderFeaturedRow(fv) {
    return `
      <div class="article-row">
        <div>
          <span class="badge badge-featured" style="margin-right:6px;">Featured</span>
          <a href="${esc(fv.url)}" target="_blank" rel="noopener">${esc(fv.title)}</a>
        </div>
        <span class="article-score">${fv.score ? fv.score.toFixed(2) : ''}</span>
      </div>
    `;
  }

  function renderArticleRow(a, label) {
    return `
      <div class="article-row">
        <div>
          ${label ? `<span class="badge badge-featured" style="margin-right:6px;">${esc(label)}</span>` : ''}
          <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>
        </div>
        <span class="article-score">${a.score ? a.score.toFixed(2) : ''}</span>
      </div>
    `;
  }

  function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  // ── Go ─────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', main);
  } else {
    main();
  }
})();
