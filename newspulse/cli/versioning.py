# coding=utf-8
"""Version check helpers for the CLI."""

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

from newspulse import __version__
from newspulse.core.config_paths import (
    get_config_layout,
    resolve_ai_interests_path,
    resolve_frequency_words_path,
    resolve_prompt_path,
    resolve_timeline_path,
)


def _parse_version(version_str: str) -> Tuple[int, int, int]:
    """解析版本号字符串为元组"""
    try:
        parts = version_str.strip().split(".")
        if len(parts) >= 3:
            return int(parts[0]), int(parts[1]), int(parts[2])
        return 0, 0, 0
    except (ValueError, AttributeError, TypeError):
        return 0, 0, 0

def _compare_version(local: str, remote: str) -> str:
    """比较版本号，返回状态文字"""
    local_tuple = _parse_version(local)
    remote_tuple = _parse_version(remote)

    if local_tuple < remote_tuple:
        return "⚠️ 需要更新"
    elif local_tuple > remote_tuple:
        return "🔮 超前版本"
    else:
        return "✅ 已是最新"

def _fetch_remote_version(version_url: str, proxy_url: Optional[str] = None) -> Optional[str]:
    """获取远程版本号"""
    try:
        proxies = None
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/plain, */*",
            "Cache-Control": "no-cache",
        }

        response = requests.get(version_url, proxies=proxies, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text.strip()
    except Exception as e:
        print(f"[版本检查] 获取远程版本失败: {e}")
        return None

def _parse_config_versions(content: str) -> Dict[str, str]:
    """解析配置文件版本内容为字典"""
    versions = {}
    try:
        if not content:
            return versions
        for line in content.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            name, version = line.split("=", 1)
            versions[name.strip()] = version.strip()
    except Exception as e:
        print(f"[版本检查] 解析配置版本失败: {e}")
    return versions

def check_all_versions(
    version_url: str,
    configs_version_url: Optional[str] = None,
    proxy_url: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    统一版本检查：程序版本 + 配置文件版本

    Args:
        version_url: 远程程序版本检查 URL
        configs_version_url: 远程配置文件版本检查 URL (返回格式: filename=version)
        proxy_url: 代理 URL

    Returns:
        (need_update, remote_version): 程序是否需要更新及远程版本号
    """
    # 获取远程版本
    remote_version = _fetch_remote_version(version_url, proxy_url)

    # 获取远程配置版本（如果有提供 URL）
    remote_config_versions = {}
    if configs_version_url:
        content = _fetch_remote_version(configs_version_url, proxy_url)
        if content:
            remote_config_versions = _parse_config_versions(content)

    print("=" * 60)
    print("版本检查")
    print("=" * 60)

    if remote_version:
        print(f"远程程序版本: {remote_version}")
    else:
        print("远程程序版本: 获取失败")

    if configs_version_url:
        if remote_config_versions:
            print(f"远程配置清单: 获取成功 ({len(remote_config_versions)} 个文件)")
        else:
            print("远程配置清单: 获取失败或为空")

    print("-" * 60)

    program_status = _compare_version(__version__, remote_version) if remote_version else "(无法比较)"
    print(f"  主程序版本: {__version__} {program_status}")

    layout = get_config_layout()
    config_files = [
        layout.config_path,
        resolve_timeline_path(config_root=layout.config_root),
        resolve_frequency_words_path(config_root=layout.config_root),
        resolve_ai_interests_path(config_root=layout.config_root),
        resolve_prompt_path("ai_analysis_prompt.txt", config_root=layout.config_root),
        resolve_prompt_path("ai_translation_prompt.txt", config_root=layout.config_root),
    ]

    version_pattern = re.compile(r"Version:\s*(\d+\.\d+\.\d+)", re.IGNORECASE)

    for config_file in config_files:
        if not config_file.exists():
            print(f"  {config_file.name}: 文件不存在")
            continue

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                local_version = None
                for i, line in enumerate(f):
                    if i >= 20:
                        break
                    match = version_pattern.search(line)
                    if match:
                        local_version = match.group(1)
                        break

                # 获取该文件的远程版本
                target_remote_version = remote_config_versions.get(config_file.name)

                if local_version:
                    if target_remote_version:
                        status = _compare_version(local_version, target_remote_version)
                        print(f"  {config_file.name}: {local_version} {status}")
                    else:
                        print(f"  {config_file.name}: {local_version} (未找到远程版本)")
                else:
                    print(f"  {config_file.name}: 未找到本地版本号")
        except Exception as e:
            print(f"  {config_file.name}: 读取失败 - {e}")

    print("=" * 60)

    # 返回程序版本的更新状态
    if remote_version:
        need_update = _parse_version(__version__) < _parse_version(remote_version)
        return need_update, remote_version if need_update else None
    return False, None
