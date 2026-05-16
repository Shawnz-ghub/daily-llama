/**
 * feed-loader.js — The Daily Llama
 *
 * Fetches ../feed.json and renders: video carousel, news cards,
 * novel findings, empty-day banner, and error banners.
 * Pure vanilla JS — no framework, no dependencies.
 * v5: infinite-scroll cover-flow carousel with tiered card sizing
 */

(function () {
  'use strict';

  const FEED_URL = '../feed.json';

  // ── Containers ──────────────────────────────────────────
  var newsGrid           = document.getElementById('news-grid');
  var novelContainer     = document.getElementById('novel-container');
  var emptyBanner        = document.getElementById('empty-banner');
  var errorBanner        = document.getElementById('error-banner');
  var genStatus          = document.getElementById('gen-status');

  async function main() {
    try {
      var resp = await fetch(FEED_URL);
      if (!resp.ok) throw new Error('HTTP ' + resp.status + ': ' + resp.statusText);
      var feed = await resp.json();
      render(feed);
    } catch (err) {
      showError(err.message);
    }
  }

  function render(feed) {
    if (genStatus && feed.generation) {
      genStatus.textContent = 'Generated ' + feed.generation.generated_at + ' \u2014 ' + feed.generation.status;
      if (feed.generation.failed_steps && feed.generation.failed_steps.length) {
        genStatus.textContent += ' (partial: ' + feed.generation.failed_steps.join(', ') + ')';
      }
    }
    if (feed.empty_day && emptyBanner) {
      emptyBanner.classList.remove('hidden');
    } else if (emptyBanner) {
      emptyBanner.classList.add('hidden');
    }

    initCoverFlow();

    if (feed.news_cards && feed.news_cards.length && newsGrid) {
      renderNewsCards(feed.news_cards);
    } else if (newsGrid) {
      newsGrid.innerHTML = '<p class="text-muted">No news articles today.</p>';
    }
    if (feed.novel_findings && feed.novel_findings.length && novelContainer) {
      renderNovelFindings(feed.novel_findings);
    } else if (novelContainer) {
      novelContainer.classList.add('hidden');
    }
  }

  // ── Infinite Cover Flow ────────────────────────────────
  function initCoverFlow() {
    var carousel = document.getElementById('video-carousel');
    if (!carousel) return;

  var originals = carousel.querySelectorAll('.video-carousel-card');
    if (originals.length < 2) return;

    var originalsArray = Array.prototype.slice.call(originals);
    var cardCount = originalsArray.length;

    // Clone cards 3x for infinite scroll
    for (var copy = 1; copy < 3; copy++) {
      for (var ci = 0; ci < cardCount; ci++) {
        carousel.appendChild(originalsArray[ci].cloneNode(true));
      }
    }

    // Refresh — all cards including clones
    var allCards = carousel.querySelectorAll('.video-carousel-card');
    var total = allCards.length;
    var cardW = 320; // matches CSS width
    var edgeGap = 20; // equal visual gap between all card edges (halved again from 40)

    // Start at middle of the first clone set so we can scroll both directions
    var currentIndex = cardCount;
    var maxIndex = cardCount * 2; // scrollable range

    // ── Equal-spacing layout: each card placed at previous card's edge + gap ──
    function layoutCards() {
      var carouselRect = carousel.getBoundingClientRect();
      var centerX = carouselRect.left + carouselRect.width / 2;

      // Determine scale for a given offset from center
      function getScale(offset) {
        var a = Math.abs(offset);
        return a === 0 ? 1.56 : a === 1 ? 1.14 : a === 2 ? 0.9 : 0.75;
      }
      function getOpacity(offset) {
        var a = Math.abs(offset);
        return a === 0 ? 1 : a === 1 ? 0.85 : a === 2 ? 0.6 : 0.3;
      }
      function getZ(offset) {
        var a = Math.abs(offset);
        return a === 0 ? 10 : a === 1 ? 5 : a === 2 ? 2 : 1;
      }

      // Position every card around centerX by chaining translateX values.
      // With default transform-origin (50% 50%), a card at translateX(L) scale(S)
      // has its visual center at (L + 160). So L_center = centerX - 160.
      // Chaining: L_{i+1} = L_i + 160*(S_i + S_{i+1}) + edgeGap

      var centerS = getScale(0);
      var centerL = centerX - 160;
      allCards[currentIndex].style.transform = 'translateX(' + centerL + 'px) scale(' + centerS + ')';
      allCards[currentIndex].style.opacity = 1;
      allCards[currentIndex].style.zIndex = 10;

      // Right side
      var prevL = centerL, prevS = centerS;
      for (var i = currentIndex + 1; i < total; i++) {
        var S = getScale(i - currentIndex);
        var L = prevL + 160 * (prevS + S) + edgeGap;
        allCards[i].style.transform = 'translateX(' + L + 'px) scale(' + S + ')';
        allCards[i].style.opacity = getOpacity(i - currentIndex);
        allCards[i].style.zIndex = getZ(i - currentIndex);
        prevL = L; prevS = S;
      }

      // Left side
      var prevL = centerL, prevS = centerS;
      for (var i = currentIndex - 1; i >= 0; i--) {
        var offset = -(i - currentIndex);
        var S = getScale(offset);
        var L = prevL - 160 * (prevS + S) - edgeGap;
        allCards[i].style.transform = 'translateX(' + L + 'px) scale(' + S + ')';
        allCards[i].style.opacity = getOpacity(-offset);
        allCards[i].style.zIndex = getZ(offset);
        prevL = L; prevS = S;
      }
    }

    // ── Scroll to next/prev card ──
    function scrollTo(delta) {
      currentIndex += delta;
      // Wrap around at boundaries
      if (currentIndex < cardCount) currentIndex += cardCount;
      if (currentIndex >= maxIndex) currentIndex -= cardCount;
      layoutCards();
    }

    // ── Wheel → scroll cards ──
    carousel.addEventListener('wheel', function(e) {
      e.preventDefault();
      var delta = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
      if (delta < -30) scrollTo(-1);
      if (delta > 30) scrollTo(1);
    }, { passive: false });

    // ── Resize ──
    window.addEventListener('resize', layoutCards);

    // Initial layout
    requestAnimationFrame(layoutCards);

    // Re-layout after images load
    var imgs = carousel.querySelectorAll('img');
    var loaded = 0;
    var totalImgs = imgs.length;
    if (totalImgs === 0) return;
    imgs.forEach(function(img) {
      if (img.complete) { loaded++; if (loaded === totalImgs) requestAnimationFrame(layoutCards); }
      else { img.addEventListener('load', function() { loaded++; if (loaded === totalImgs) requestAnimationFrame(layoutCards); }); }
    });
  }

  // ── News Cards ─────────────────────────────────────
  function renderNewsCards(items) {
    if (!newsGrid) return;
    newsGrid.innerHTML = items.map(function(nc) {
      var thumbHtml = nc.thumbnail ? '<div class="news-thumb"><img src="' + esc(nc.thumbnail) + '" alt="" loading="lazy"></div>' : '';
      var excerptHtml = nc.summary ? '<p class="card-excerpt">' + esc(nc.summary) + '</p>' : '';
      return '<div class="card news-card" onclick="openArticle(this,\'' + esc(nc.url) + '\')" style="cursor:pointer;">' +
        thumbHtml +
        '<div class="card-title">' +
          esc(nc.title) +
        '</div>' +
        '<div class="card-meta">' +
          '<span>' + fmtDate(nc.published_date) + '</span>' +
        '</div>' +
        excerptHtml +
      '</div>';
    }).join('');
  }

  // ── Novel Findings ─────────────────────────────────
  function renderNovelFindings(items) {
    if (!novelContainer) return;
    var list = novelContainer.querySelector('#novel-list');
    if (!list) return;
    list.innerHTML = items.map(function(nf) {
      return '<div class="novel-item">' +
        '<div class="novel-source">' + esc(nf.source || '') + '</div>' +
        '<a href="' + esc(nf.url) + '" target="_blank" rel="noopener" style="font-size:0.85rem;">' + esc(nf.title) + '</a>' +
        '<div class="novel-note">' + esc(nf.prospecting_note || '') + '</div>' +
      '</div>';
    }).join('');
  }

  // ── Error banner ───────────────────────────────────
  function showError(msg) {
    if (errorBanner) {
      errorBanner.classList.remove('hidden');
      var el = errorBanner.querySelector('.error-msg');
      if (el) el.textContent = msg;
    }
  }

  // ── Helpers ────────────────────────────────────────
  function esc(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function fmtDate(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch (_) { return iso.slice(0, 10); }
  }

  // ── Go ─────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', main);
  } else {
    main();
  }
})();
