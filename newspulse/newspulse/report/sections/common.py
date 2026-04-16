# coding=utf-8
"""Common helpers for report sections."""


def add_section_divider(content: str) -> str:
    """Inject the shared divider class into a section wrapper."""
    if not content or 'class="' not in content:
        return content

    first_class_pos = content.find('class="')
    if first_class_pos == -1:
        return content

    insert_pos = first_class_pos + len('class="')
    return content[:insert_pos] + "section-divider " + content[insert_pos:]
