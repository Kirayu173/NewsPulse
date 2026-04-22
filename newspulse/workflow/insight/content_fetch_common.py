# coding=utf-8
"""Shared helpers for sync and async insight content fetching."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from bs4 import BeautifulSoup

from newspulse.crawler.sources.base import strip_html


def extract_hn_external_url(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    selectors = [
        ".titleline a[href]",
        "a.titlelink[href]",
        "main a[href^='http']",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        href = str(node.get("href") or "").strip() if node else ""
        if href and "news.ycombinator.com" not in href:
            return href
    return ""


def extract_hn_item_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    blocks: list[str] = []
    for selector in (".toptext", ".comment .commtext", ".comment-tree .commtext"):
        for node in soup.select(selector):
            text = strip_html(str(node))
            cleaned = trim_text(text, limit=500)
            if cleaned and cleaned not in blocks:
                blocks.append(cleaned)
            if len(blocks) >= 6:
                break
        if blocks:
            break
    return "\n\n".join(blocks).strip()


def format_repo_stats(repo: Mapping[str, Any]) -> str:
    parts: list[str] = []
    language = str(repo.get("language") or "").strip()
    if language:
        parts.append(f"language={language}")
    for label, key in (("stars_today", "stars_today"), ("stars_total", "stars_total"), ("forks_total", "forks_total")):
        value = repo.get(key)
        if value not in (None, ""):
            parts.append(f"{label}={value}")
    pushed_at = str(repo.get("pushed_at") or "").strip()
    if pushed_at:
        parts.append(f"updated={pushed_at[:10]}")
    created_at = str(repo.get("created_at") or "").strip()
    if created_at:
        parts.append(f"created={created_at[:10]}")
    flags = []
    if bool(repo.get("archived")):
        flags.append("archived")
    if bool(repo.get("fork")):
        flags.append("fork")
    if flags:
        parts.append("flags=" + ",".join(flags))
    return "Repo stats: " + "; ".join(parts) if parts else ""


def hash_text(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest() if text else ""


def is_meaningful_text(text: str, min_length: int = 120) -> bool:
    normalized = " ".join((text or "").split())
    return len(normalized) >= min_length


def trim_text(text: str, *, limit: int) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def first_line(text: str) -> str:
    for line in str(text or "").splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""
