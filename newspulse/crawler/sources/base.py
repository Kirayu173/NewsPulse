# coding=utf-8
"""
Common helpers for builtin source handlers.
"""

from __future__ import annotations

import base64
import hashlib
import random
import string
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup, FeatureNotFound


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


@dataclass
class SourceItem:
    """Normalized hotlist item."""

    title: str
    url: str = ""
    mobile_url: str = ""


class SourceClient:
    """Small requests wrapper shared by builtin sources."""

    def __init__(self, proxy_url: Optional[str] = None, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if proxy_url:
            self.session.proxies.update({"http": proxy_url, "https": proxy_url})

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self.request("GET", url, **kwargs).text

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.request("GET", url, **kwargs).json()

    def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        return self.request("GET", url, **kwargs).content

    def get_soup(self, url: str, **kwargs: Any) -> BeautifulSoup:
        return make_soup(self.get_text(url, **kwargs))

    def get_feed(self, url: str, **kwargs: Any) -> feedparser.FeedParserDict:
        return feedparser.parse(self.get_bytes(url, **kwargs))


def make_soup(text: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(text, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(text, "html.parser")


def strip_html(html: str) -> str:
    if not html:
        return ""
    return make_soup(html).get_text("\n", strip=True)


def absolute_url(base_url: str, url: str) -> str:
    return urljoin(base_url, url or "")


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def sha1_hex(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def base64_encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def random_device_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    lengths = (10, 6, 6, 6, 14)
    parts = [
        "".join(random.choice(alphabet) for _ in range(length))
        for length in lengths
    ]
    return "-".join(parts)
