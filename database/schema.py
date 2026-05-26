import sqlite3
import os
from typing import Dict, Any


DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "data/tourism_cache.db")


def get_db_path() -> str:
    return DATABASE_PATH


def set_db_path(path: str) -> None:
    global DATABASE_PATH
    DATABASE_PATH = path


def get_connection() -> sqlite3.Connection:
    path = DATABASE_PATH
    db_dir = os.path.dirname(path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    if db_dir and os.path.isdir(db_dir) and not os.access(db_dir, os.W_OK):
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    path = DATABASE_PATH
    if os.path.exists(path):
        return
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


SCHEMA_SQL: str = """
-- ================================================================
-- Tourism Data Caching System - Database Schema
-- ================================================================

-- 1. API response cache - saves raw API responses
CREATE TABLE IF NOT EXISTS api_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,          -- e.g. 'mots', 'tat', 'data.go.th'
    endpoint        TEXT    NOT NULL,          -- API endpoint path
    params_hash     TEXT    NOT NULL,          -- SHA256 of sorted params JSON
    response        TEXT    NOT NULL,          -- Full JSON response
    status_code     INTEGER DEFAULT 200,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at      TEXT    NOT NULL,          -- When this cache entry expires
    last_accessed   TEXT    DEFAULT (datetime('now')),
    hit_count       INTEGER DEFAULT 1,         -- Times served from cache
    UNIQUE(source, endpoint, params_hash)
);

CREATE INDEX IF NOT EXISTS idx_api_cache_lookup
    ON api_cache(source, endpoint, params_hash);
CREATE INDEX IF NOT EXISTS idx_api_cache_expires
    ON api_cache(expires_at);

-- 2. API usage tracking for rate limiting
CREATE TABLE IF NOT EXISTS api_usage (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    date     TEXT    NOT NULL,                 -- e.g. '2026-05-26'
    source   TEXT    NOT NULL,
    calls    INTEGER DEFAULT 0,
    UNIQUE(date, source)
);

-- 3. Normalized tourism data
CREATE TABLE IF NOT EXISTS tourism_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT    NOT NULL,          -- accommodation | attraction | restaurant | event | transport
    source          TEXT    NOT NULL,          -- which API provided this
    province        TEXT,
    district        TEXT,
    name_th         TEXT,
    name_en         TEXT,
    latitude        REAL,
    longitude       REAL,
    address         TEXT,
    phone           TEXT,
    website         TEXT,
    tags            TEXT,                     -- JSON array
    details         TEXT,                     -- JSON blob for extra fields
    raw_source      TEXT,
    fetched_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, province, category, name_th)
);

CREATE INDEX IF NOT EXISTS idx_tourism_province
    ON tourism_data(province);
CREATE INDEX IF NOT EXISTS idx_tourism_category
    ON tourism_data(category);
CREATE INDEX IF NOT EXISTS idx_tourism_location
    ON tourism_data(latitude, longitude);

-- 4. Provincial tourism statistics
CREATE TABLE IF NOT EXISTS province_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    province        TEXT    NOT NULL,
    year            INTEGER NOT NULL,
    month           INTEGER,
    tourists_thai   INTEGER DEFAULT 0,
    tourists_foreign INTEGER DEFAULT 0,
    revenue         REAL    DEFAULT 0,
    avg_stay_days   REAL,
    occupancy_rate  REAL,
    source          TEXT,
    fetched_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(province, year, month)
);

CREATE INDEX IF NOT EXISTS idx_stats_province_year
    ON province_stats(province, year);

-- 5. Fetcher metadata
CREATE TABLE IF NOT EXISTS fetcher_metadata (
    source       TEXT PRIMARY KEY,
    last_fetch   TEXT,
    total_calls  INTEGER DEFAULT 0,
    total_hits   INTEGER DEFAULT 0,           -- cache hits
    error_count  INTEGER DEFAULT 0,
    last_error   TEXT
);

-- 6. GD Catalog dataset metadata
CREATE TABLE IF NOT EXISTS gdcatalog_datasets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id   TEXT    NOT NULL UNIQUE,
    name         TEXT,
    title        TEXT,
    notes        TEXT,
    category     TEXT,
    organization TEXT,
    fetched_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_gdcatalog_datasets_cat
    ON gdcatalog_datasets(category);

-- 7. GD Catalog downloaded data
CREATE TABLE IF NOT EXISTS gdcatalog_data (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id   TEXT    NOT NULL,
    resource_id  TEXT,
    category     TEXT,
    province     TEXT,
    columns      TEXT,
    row_data     TEXT    NOT NULL,
    fetched_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_gdcatalog_data_cat
    ON gdcatalog_data(category);
CREATE INDEX IF NOT EXISTS idx_gdcatalog_data_province
    ON gdcatalog_data(province);
CREATE INDEX IF NOT EXISTS idx_gdcatalog_data_dataset
    ON gdcatalog_data(dataset_id);
""";
