-- News storage schema.

CREATE TABLE IF NOT EXISTS platforms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    url TEXT DEFAULT '',
    mobile_url TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    source_metadata_json TEXT DEFAULT '{}',
    first_crawl_time TEXT NOT NULL,
    last_crawl_time TEXT NOT NULL,
    crawl_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (platform_id) REFERENCES platforms(id)
);

CREATE TABLE IF NOT EXISTS title_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_item_id INTEGER NOT NULL,
    old_title TEXT NOT NULL,
    new_title TEXT NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (news_item_id) REFERENCES news_items(id)
);

CREATE TABLE IF NOT EXISTS rank_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_item_id INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    crawl_time TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (news_item_id) REFERENCES news_items(id)
);

CREATE TABLE IF NOT EXISTS crawl_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_time TEXT NOT NULL UNIQUE,
    total_items INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crawl_source_status (
    crawl_record_id INTEGER NOT NULL,
    platform_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed')),
    PRIMARY KEY (crawl_record_id, platform_id),
    FOREIGN KEY (crawl_record_id) REFERENCES crawl_records(id),
    FOREIGN KEY (platform_id) REFERENCES platforms(id)
);

CREATE TABLE IF NOT EXISTS crawl_source_failures (
    crawl_record_id INTEGER NOT NULL,
    platform_id TEXT NOT NULL,
    resolved_source_id TEXT NOT NULL,
    exception_type TEXT DEFAULT '',
    message TEXT DEFAULT '',
    attempts INTEGER DEFAULT 1,
    retryable INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (crawl_record_id, platform_id),
    FOREIGN KEY (crawl_record_id) REFERENCES crawl_records(id),
    FOREIGN KEY (platform_id) REFERENCES platforms(id)
);

CREATE TABLE IF NOT EXISTS period_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_date TEXT NOT NULL,
    period_key TEXT NOT NULL,
    action TEXT NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(execution_date, period_key, action)
);

CREATE TABLE IF NOT EXISTS article_contents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_url TEXT NOT NULL UNIQUE,
    source_type TEXT DEFAULT '',
    source_id TEXT DEFAULT '',
    source_name TEXT DEFAULT '',
    source_kind TEXT DEFAULT '',
    original_url TEXT DEFAULT '',
    final_url TEXT DEFAULT '',
    title TEXT DEFAULT '',
    excerpt TEXT DEFAULT '',
    content_text TEXT DEFAULT '',
    content_markdown TEXT DEFAULT '',
    content_hash TEXT DEFAULT '',
    published_at TEXT DEFAULT '',
    author TEXT DEFAULT '',
    extractor_name TEXT DEFAULT '',
    fetch_status TEXT DEFAULT '',
    error_type TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    trace_json TEXT DEFAULT '{}',
    fetched_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_news_platform ON news_items(platform_id);
CREATE INDEX IF NOT EXISTS idx_news_crawl_time ON news_items(last_crawl_time);
CREATE INDEX IF NOT EXISTS idx_news_title ON news_items(title);
CREATE UNIQUE INDEX IF NOT EXISTS idx_news_url_platform
    ON news_items(url, platform_id) WHERE url != '';
CREATE INDEX IF NOT EXISTS idx_crawl_status_record ON crawl_source_status(crawl_record_id);
CREATE INDEX IF NOT EXISTS idx_crawl_failures_record ON crawl_source_failures(crawl_record_id);
CREATE INDEX IF NOT EXISTS idx_rank_history_news ON rank_history(news_item_id);
CREATE INDEX IF NOT EXISTS idx_rank_history_news_crawl_time ON rank_history(news_item_id, crawl_time);
CREATE INDEX IF NOT EXISTS idx_news_platform_crawl_time ON news_items(platform_id, last_crawl_time);
CREATE INDEX IF NOT EXISTS idx_period_exec_lookup
    ON period_executions(execution_date, period_key, action);
CREATE INDEX IF NOT EXISTS idx_article_content_source
    ON article_contents(source_id, source_kind);
