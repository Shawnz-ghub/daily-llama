/**
 * archive-loader.js — The Daily LLama 
 *
 * Loads archive snapshot JSON files from ../archive/ and renders them
 * as daily feed snapshots. Pure vanilla JS.
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
      if (!resp.ok) throw new Error('HTTP ' + resp.status + ': ' + resp.statusText);
      const entries = await resp.json();

      if (!entries.length) {
        container.innerHTML = '<p class="text-center" style="color:var(--text-muted);padding:40px 0;">No archived feeds yet.</p>';
        if (loadingEl) loadingEl.classList.add('hidden');
        return;
      }

      // Load each entry file (daily or monthly)
      const dailyGroup = {};
      for (const slug of entries.slice(0, 90)) {
        try {
          const resp2 = await fetch(ARCHIVE_DIR + slug + '.json');
          if (!resp2.ok) continue;
          const data = await resp2.json();

          // Determine display date from slug
          let label;
          if (slug.length === 10) {
            // Daily: YYYY-MM-DD
            const y = parseInt(slug.slice(0, 4));
            const m = parseInt(slug.slice(5, 7)) - 1;
            const d = parseInt(slug.slice(8, 10));
            label = new Date(y, m, d).toLocaleString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
          } else {
            // Monthly: YYYY-MM
            const y = parseInt(slug.slice(0, 4));
            const m = parseInt(slug.slice(5, 7)) - 1;
            label = new Date(y, m).toLocaleString('en-US', { month: 'long', year: 'numeric' }) + ' (Monthly)';
          }

          dailyGroup[slug] = {
            slug: slug,
            label: label,
            articles: data.news_cards || [],
            featured: data.featured_video || null,
            runner_ups: data.runner_ups || [],
          };
        } catch (_) {
          // Skip entries that fail to load
        }
      }

      render(dailyGroup);
    } catch (err) {
      if (errorEl) {
        errorEl.classList.remove('hidden');
        document.getElementById('archive-error-msg').textContent = 'Failed to load archive: ' + err.message;
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('hidden');
    }
  }

  function render(dailyGroup) {
    const slugs = Object.keys(dailyGroup).sort().reverse();
    let html = '';

    for (const slug of slugs) {
      const d = dailyGroup[slug];
      const total = d.articles.length + (d.featured ? 1 : 0) + d.runner_ups.length;
      html += '<div class="archive-month"><div class="archive-header" onclick="this.nextElementSibling.classList.toggle(&#39;hidden&#39;)"><h3>' + esc(d.label) + '</h3><span class="archive-count">' + total + ' article' + (total !== 1 ? 's' : '') + '</span></div>';
      html += '<div class="archive-articles hidden">';
      if (d.featured) html += renderFeaturedRow(d.featured);
      if (d.featured && d.runner_ups.length) {
        html += '<div class="archive-separator"></div>';
      }
      for (const ru of d.runner_ups) {
        html += renderArticleRow(ru, 'Runner-up');
      }
      if (d.runner_ups.length && d.articles.length) {
        html += '<div class="archive-separator"></div>';
      }
      for (const a of d.articles) {
        html += renderArticleRow(a, '');
      }
      html += '</div></div>';
    }

    container.innerHTML = html || '<p class="text-center" style="color:var(--text-muted);padding:40px 0;">No archives to display.</p>';
  }

  function renderFeaturedRow(fv) {
    return '<div class="article-row"><div><span class="badge badge-featured" style="margin-right:6px;">Featured</span><a href="' + esc(fv.url) + '" target="_blank" rel="noopener">' + esc(fv.title) + '</a></div><span class="article-score">' + (fv.score ? fv.score.toFixed(2) : '') + '</span></div>';
  }

  function renderArticleRow(a, label) {
    return '<div class="article-row"><div>' + (label ? '<span class="badge badge-featured" style="margin-right:6px;">' + esc(label) + '</span>' : '') + '<a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></div><span class="article-score">' + (a.score ? a.score.toFixed(2) : '') + '</span></div>';
  }

  function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  // — Go ─
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', main);
  } else {
    main();
  }
})();
