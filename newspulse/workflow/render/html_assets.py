# coding=utf-8
"""Embedded CSS and JavaScript for the card-first HTML report."""

from __future__ import annotations


def _page_styles() -> str:
    return """
        :root {
            color-scheme: light;
            --bg: #f4efe8;
            --paper: rgba(255, 252, 247, 0.96);
            --panel: #fff8f0;
            --panel-strong: #fff4e4;
            --ink: #17202d;
            --muted: #697383;
            --accent: #c35b17;
            --accent-deep: #8d3600;
            --accent-soft: #f6dcc4;
            --accent-ghost: rgba(195, 91, 23, 0.08);
            --border: rgba(195, 91, 23, 0.14);
            --shadow: 0 24px 70px rgba(59, 31, 8, 0.10);
        }

        * { box-sizing: border-box; }

        html { scroll-behavior: smooth; }

        body {
            margin: 0;
            padding: 22px;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 10%, rgba(195, 91, 23, 0.12), transparent 30%),
                radial-gradient(circle at 90% 18%, rgba(38, 91, 122, 0.08), transparent 26%),
                linear-gradient(180deg, #f8f3ec 0%, var(--bg) 100%);
            font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            line-height: 1.7;
        }

        button,
        input,
        textarea,
        select {
            font: inherit;
        }

        .shell {
            max-width: 1120px;
            margin: 0 auto;
            background: var(--paper);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: var(--shadow);
            backdrop-filter: blur(12px);
        }

        .hero {
            position: relative;
            overflow: hidden;
            padding: 44px 38px 34px;
            background:
                radial-gradient(circle at top right, rgba(255, 255, 255, 0.18), transparent 30%),
                linear-gradient(135deg, rgba(195, 91, 23, 0.98), rgba(118, 52, 15, 0.94));
            color: #fff;
        }

        .hero::after {
            content: "";
            position: absolute;
            inset: auto -90px -110px auto;
            width: 260px;
            height: 260px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.10);
            filter: blur(8px);
        }

        .hero h1 {
            position: relative;
            z-index: 1;
            margin: 0;
            font-size: clamp(30px, 5vw, 48px);
            line-height: 1.08;
            letter-spacing: -0.03em;
        }

        .hero-meta {
            position: relative;
            z-index: 1;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
        }

        .hero-pill,
        .story-badge,
        .mini-chip,
        .story-meta-pill,
        .story-action,
        .filter-chip,
        .section-toggle {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }

        .hero-pill {
            padding: 8px 12px;
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.18);
        }

        .hero-banner {
            position: relative;
            z-index: 1;
            margin-top: 16px;
            padding: 10px 14px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.18);
            font-size: 14px;
        }

        .content {
            padding: 28px 30px 36px;
        }

        .overview-strip,
        .story-feed,
        .summary-section,
        .aggregate-section {
            margin-top: 24px;
            animation: rise-in 0.55s ease both;
        }

        .story-feed h2,
        .summary-section h2,
        .aggregate-section h2 {
            margin: 0 0 10px;
            font-size: 24px;
            line-height: 1.15;
        }

        .overview-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 14px;
        }

        .overview-card,
        .story-card,
        .summary-card,
        .aggregate-card,
        .control-card {
            animation: rise-in 0.6s ease both;
        }

        .overview-card {
            padding: 18px 18px 16px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 245, 238, 0.96));
            border: 1px solid var(--border);
        }

        .overview-label {
            font-size: 12px;
            color: var(--muted);
        }

        .overview-value {
            margin-top: 8px;
            font-size: 26px;
            font-weight: 800;
            line-height: 1.05;
        }

        .overview-value.small {
            font-size: 16px;
            line-height: 1.4;
        }

        .control-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 14px;
            margin-top: 14px;
        }

        .control-card {
            padding: 18px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(251, 247, 241, 0.90));
            border: 1px solid var(--border);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
        }

        .control-label {
            display: block;
            margin-bottom: 10px;
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .search-row {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .search-input {
            flex: 1;
            min-width: 0;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: rgba(255, 255, 255, 0.86);
            padding: 12px 14px;
            color: var(--ink);
            outline: none;
            transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
        }

        .search-input:focus {
            border-color: rgba(195, 91, 23, 0.44);
            box-shadow: 0 0 0 4px rgba(195, 91, 23, 0.12);
            background: #fff;
        }

        .search-clear,
        .section-toggle,
        .filter-chip,
        .story-badge.source {
            border: 1px solid transparent;
            cursor: pointer;
            transition: transform 0.18s ease, opacity 0.18s ease, background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
        }

        .search-clear {
            padding: 12px 14px;
            border-radius: 8px;
            background: var(--accent-ghost);
            color: var(--accent-deep);
            border-color: rgba(195, 91, 23, 0.12);
            white-space: nowrap;
        }

        .search-clear:hover,
        .search-clear:focus-visible,
        .section-toggle:hover,
        .section-toggle:focus-visible,
        .filter-chip:hover,
        .filter-chip:focus-visible,
        .story-badge.source:hover,
        .story-badge.source:focus-visible {
            transform: translateY(-1px);
            opacity: 0.96;
        }

        .filter-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }

        .filter-chip {
            padding: 9px 14px;
            background: rgba(255, 255, 255, 0.82);
            color: #5c4633;
            border-color: rgba(195, 91, 23, 0.12);
        }

        .filter-chip.active {
            background: linear-gradient(180deg, var(--accent), var(--accent-deep));
            color: #fff;
            border-color: transparent;
        }

        .story-list {
            display: flex;
            flex-direction: column;
            gap: 22px;
            margin-top: 18px;
        }

        .story-card {
            padding: 22px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 247, 241, 0.94));
            border: 1px solid var(--border);
        }

        .story-card.is-hidden {
            display: none;
        }

        .story-head {
            display: grid;
            grid-template-columns: 58px minmax(0, 1fr);
            gap: 16px;
            align-items: start;
        }

        .story-index {
            width: 58px;
            height: 58px;
            border-radius: 8px;
            background: linear-gradient(180deg, var(--accent), var(--accent-deep));
            color: #fff;
            font-size: 22px;
            font-weight: 800;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
        }

        .story-badges,
        .story-actions,
        .chip-row,
        .story-meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .story-title {
            margin: 10px 0 12px;
            font-size: clamp(22px, 2.6vw, 30px);
            line-height: 1.24;
        }

        .story-summary-block {
            max-width: 900px;
            margin-top: 6px;
        }

        .story-summary-label {
            margin-bottom: 4px;
            color: var(--muted);
            font-size: 12px;
            font-weight: 800;
        }

        .story-summary {
            margin: 0;
            max-width: 880px;
            font-size: 16px;
            color: #334052;
            line-height: 1.75;
        }

        .story-meta-row {
            margin-top: 14px;
        }

        .story-badge {
            padding: 6px 10px;
        }

        .story-badge.source {
            background: #f2e9df;
            color: #5c4633;
        }

        .story-badge.accent {
            background: #fde7ab;
            color: #8f5600;
        }

        .story-badge.muted {
            background: #eef2f6;
            color: #5a6576;
        }

        .story-meta-pill {
            padding: 6px 10px;
            background: rgba(242, 233, 223, 0.78);
            color: #624f3e;
        }

        .story-actions {
            margin-top: 16px;
        }

        .story-action {
            padding: 8px 12px;
            text-decoration: none;
            background: var(--accent);
            color: #fff;
            transition: transform 0.18s ease, opacity 0.18s ease;
        }

        .story-action:hover {
            transform: translateY(-1px);
            opacity: 0.94;
        }

        .story-action.secondary {
            background: transparent;
            color: var(--accent-deep);
            border: 1px solid rgba(195, 91, 23, 0.18);
        }

        .story-empty,
        .empty-state {
            padding: 26px 24px;
            text-align: center;
            color: var(--muted);
            font-size: 15px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.75);
            border: 1px dashed rgba(195, 91, 23, 0.18);
        }

        .story-empty {
            margin-top: 18px;
        }

        .story-empty[hidden],
        .aggregate-content[hidden] {
            display: none;
        }

        .aggregate-head {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-start;
            flex-wrap: wrap;
        }

        .aggregate-heading {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .mini-chip {
            padding: 5px 9px;
            background: var(--accent-soft);
            color: var(--accent-deep);
        }

        .section-toggle {
            padding: 10px 14px;
            background: rgba(255, 255, 255, 0.86);
            color: var(--accent-deep);
            border-color: rgba(195, 91, 23, 0.14);
        }

        .aggregate-grid {
            margin-top: 18px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
        }

        .aggregate-card {
            padding: 18px 18px 16px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 247, 241, 0.94));
            border: 1px solid var(--border);
        }

        .aggregate-card h3 {
            margin: 0 0 10px;
            font-size: 19px;
        }

        .aggregate-card p {
            margin: 0;
            color: #303a48;
            font-size: 14px;
        }

        .aggregate-note {
            margin: 8px 0 0;
            color: var(--muted);
        }

        .summary-list {
            display: flex;
            flex-direction: column;
            gap: 14px;
            margin-top: 14px;
        }

        .report-summary-list {
            margin-bottom: 18px;
        }

        .summary-subhead {
            margin: 16px 0 0;
            font-size: 18px;
        }

        .summary-card {
            padding: 18px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 247, 241, 0.94));
            border: 1px solid var(--border);
        }

        .summary-card-head {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
        }

        .summary-kind,
        .summary-count {
            display: inline-flex;
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 12px;
            font-weight: 700;
        }

        .summary-kind {
            background: #e8f1fb;
            color: #25587a;
        }

        .summary-count {
            background: rgba(242, 233, 223, 0.78);
            color: #624f3e;
        }

        .summary-card h3 {
            margin: 10px 0 6px;
            font-size: 20px;
        }

        .summary-card p {
            margin: 0;
            color: #303a48;
            font-size: 15px;
            line-height: 1.75;
        }

        .summary-meta-line {
            margin-top: 10px;
            color: var(--muted);
            font-size: 13px;
        }

        .footer {
            padding: 0 30px 30px;
            color: var(--muted);
            font-size: 13px;
        }

        @keyframes rise-in {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @media (prefers-color-scheme: dark) {
            :root {
                color-scheme: dark;
                --bg: #141a20;
                --paper: rgba(20, 25, 31, 0.92);
                --panel: #18202a;
                --panel-strong: #1d2833;
                --ink: #eef2f6;
                --muted: #aab3bf;
                --accent: #ff9d58;
                --accent-deep: #f07a2c;
                --accent-soft: rgba(255, 157, 88, 0.18);
                --accent-ghost: rgba(255, 157, 88, 0.10);
                --border: rgba(255, 157, 88, 0.16);
                --shadow: 0 24px 70px rgba(0, 0, 0, 0.32);
            }

            body {
                background:
                    radial-gradient(circle at 10% 10%, rgba(255, 157, 88, 0.08), transparent 28%),
                    radial-gradient(circle at 85% 12%, rgba(90, 163, 208, 0.10), transparent 25%),
                    linear-gradient(180deg, #10151b 0%, var(--bg) 100%);
            }

            .overview-card,
            .story-card,
            .summary-card,
            .aggregate-card,
            .control-card,
            .story-empty,
            .empty-state {
                background: linear-gradient(180deg, rgba(29, 36, 45, 0.96), rgba(20, 26, 34, 0.96));
            }

            .search-input,
            .section-toggle,
            .filter-chip,
            .search-clear {
                background: rgba(14, 19, 25, 0.86);
                color: var(--ink);
            }

            .story-badge.source,
            .story-meta-pill {
                background: rgba(255, 157, 88, 0.12);
                color: #ffd2b0;
            }

            .story-badge.muted {
                background: rgba(111, 130, 149, 0.18);
                color: #d3dce7;
            }

            .story-badge.accent {
                background: rgba(255, 218, 117, 0.16);
                color: #ffe29d;
            }

            .story-summary,
            .summary-card p,
            .aggregate-card p {
                color: #d6dee8;
            }
        }

        @media (max-width: 900px) {
            .story-head {
                grid-template-columns: 1fr;
            }

            .story-index {
                width: 60px;
                height: 60px;
                border-radius: 8px;
            }
        }

        @media (max-width: 720px) {
            body {
                padding: 14px;
            }

            .hero {
                padding: 30px 22px 24px;
            }

            .content {
                padding: 18px;
            }

            .story-card,
            .control-card {
                padding: 18px;
                border-radius: 8px;
            }

            .overview-strip {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .aggregate-grid {
                grid-template-columns: 1fr;
            }

            .search-row {
                flex-direction: column;
                align-items: stretch;
            }

            .search-clear {
                width: 100%;
            }
        }
    """


def _page_script() -> str:
    return """
    (() => {
        const storyCards = Array.from(document.querySelectorAll('[data-story-card]'));
        const emptyState = document.querySelector('[data-story-empty]');
        const searchInput = document.querySelector('[data-story-search]');
        const clearSearchButton = document.querySelector('[data-clear-search]');
        const sourceButtons = Array.from(document.querySelectorAll('[data-source-filter]'));
        const inlineSourceButtons = Array.from(document.querySelectorAll('.js-source-filter'));
        const toggleButtons = Array.from(document.querySelectorAll('[data-toggle-target]'));

        let activeSource = 'all';

        const applyFilters = () => {
            const query = (searchInput?.value || '').trim().toLowerCase();
            let visibleCount = 0;

            storyCards.forEach((card) => {
                const searchText = (card.dataset.searchText || '').toLowerCase();
                const sourceKey = card.dataset.sourceKey || 'unknown';
                const matchesSource = activeSource === 'all' || sourceKey === activeSource;
                const matchesQuery = !query || searchText.includes(query);
                const visible = matchesSource && matchesQuery;
                card.classList.toggle('is-hidden', !visible);
                if (visible) {
                    visibleCount += 1;
                }
            });

            if (emptyState) {
                emptyState.hidden = visibleCount !== 0;
            }
        };

        const syncSourceButtons = () => {
            sourceButtons.forEach((button) => {
                const isActive = (button.dataset.sourceFilter || 'all') === activeSource;
                button.classList.toggle('active', isActive);
                button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
        };

        const setActiveSource = (nextSource) => {
            activeSource = nextSource || 'all';
            syncSourceButtons();
            applyFilters();
        };

        if (searchInput) {
            searchInput.addEventListener('input', applyFilters);
            searchInput.addEventListener('keydown', (event) => {
                if (event.key === 'Escape') {
                    searchInput.value = '';
                    applyFilters();
                }
            });
        }

        if (clearSearchButton && searchInput) {
            clearSearchButton.addEventListener('click', () => {
                searchInput.value = '';
                searchInput.focus();
                applyFilters();
            });
        }

        sourceButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const nextSource = button.dataset.sourceFilter || 'all';
                setActiveSource(nextSource == activeSource && nextSource !== 'all' ? 'all' : nextSource);
            });
        });

        inlineSourceButtons.forEach((button) => {
            button.addEventListener('click', () => {
                setActiveSource(button.dataset.sourceKey || 'all');
            });
        });

        toggleButtons.forEach((button) => {
            const targetId = button.dataset.toggleTarget;
            const target = targetId ? document.getElementById(targetId) : null;
            if (!target) {
                return;
            }
            button.addEventListener('click', () => {
                const expanded = button.getAttribute('aria-expanded') !== 'false';
                button.setAttribute('aria-expanded', expanded ? 'false' : 'true');
                target.hidden = expanded;
                button.textContent = expanded ? '展开' : '折叠';
            });
        });

        syncSourceButtons();
        applyFilters();
    })();
    """
