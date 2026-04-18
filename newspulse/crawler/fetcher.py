# coding=utf-8
"""
Builtin hotlist fetcher.
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Tuple, Union

from newspulse.crawler.sources import SourceClient, SourceItem, get_source_handler


class DataFetcher:
    """Fetch hotlist data from builtin Python sources."""

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        api_url: Optional[str] = None,
    ):
        # `api_url` is kept only for constructor compatibility.
        self.proxy_url = proxy_url
        self.api_url = api_url or "builtin"
        self.client = SourceClient(proxy_url=proxy_url)

    def fetch_data(
        self,
        id_info: Union[str, Tuple[str, str]],
        max_retries: int = 2,
        min_retry_wait: int = 3,
        max_retry_wait: int = 5,
    ) -> Tuple[Optional[List[SourceItem]], str, str]:
        """Fetch one source with retries."""
        if isinstance(id_info, tuple):
            id_value, alias = id_info
        else:
            id_value = id_info
            alias = id_value

        retries = 0
        while retries <= max_retries:
            try:
                handler = get_source_handler(id_value)
                items = handler(self.client)
                print(f"获取 {id_value} 成功（builtin，本地实现）")
                return items, id_value, alias
            except Exception as e:
                retries += 1
                if retries <= max_retries:
                    base_wait = random.uniform(min_retry_wait, max_retry_wait)
                    additional_wait = (retries - 1) * random.uniform(1, 2)
                    wait_time = base_wait + additional_wait
                    print(f"请求 {id_value} 失败: {e}. {wait_time:.2f}秒后重试...")
                    time.sleep(wait_time)
                else:
                    print(f"请求 {id_value} 失败: {e}")
                    return None, id_value, alias

        return None, id_value, alias

    def crawl_websites(
        self,
        ids_list: List[Union[str, Tuple[str, str]]],
        request_interval: int = 100,
    ) -> Tuple[Dict, Dict, List]:
        """Fetch multiple hotlist sources and normalize the old result shape."""
        results: Dict[str, Dict] = {}
        id_to_name: Dict[str, str] = {}
        failed_ids: List[str] = []

        for i, id_info in enumerate(ids_list):
            if isinstance(id_info, tuple):
                id_value, name = id_info
            else:
                id_value = id_info
                name = id_value

            id_to_name[id_value] = name
            items, _, _ = self.fetch_data(id_info)

            if items is None:
                failed_ids.append(id_value)
            else:
                results[id_value] = {}
                for index, item in enumerate(items, 1):
                    title = item.title
                    if not title:
                        continue

                    if title in results[id_value]:
                        results[id_value][title]["ranks"].append(index)
                    else:
                        results[id_value][title] = {
                            "ranks": [index],
                            "url": item.url,
                            "mobileUrl": item.mobile_url,
                        }

            if i < len(ids_list) - 1:
                actual_interval = request_interval + random.randint(-10, 20)
                actual_interval = max(50, actual_interval)
                time.sleep(actual_interval / 1000)

        print(f"成功: {list(results.keys())}, 失败: {failed_ids}")
        return results, id_to_name, failed_ids
