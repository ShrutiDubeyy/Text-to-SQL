-- This runs automatically when MySQL
-- container starts for the first time

CREATE DATABASE IF NOT EXISTS chatbot_db;
USE chatbot_db;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(50) DEFAULT 'viewer',
    allowed_tables TEXT DEFAULT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Conversations / Memory
CREATE TABLE IF NOT EXISTS conversations (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    role       VARCHAR(20) NOT NULL,
    message    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Roles
CREATE TABLE IF NOT EXISTS roles (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    can_upload  BOOLEAN DEFAULT FALSE,
    can_query   BOOLEAN DEFAULT TRUE,
    is_admin    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default roles
INSERT IGNORE INTO roles
(name, description, can_upload, can_query, is_admin)
VALUES
('admin',   'Full access',           TRUE,  TRUE, TRUE),
('analyst', 'Query + upload access', TRUE,  TRUE, FALSE),
('viewer',  'Read only access',      FALSE, TRUE, FALSE);

-- Query cache
CREATE TABLE IF NOT EXISTS _query_cache (
    cache_key  VARCHAR(64) PRIMARY KEY,
    question   TEXT,
    sql_query  TEXT,
    answer     TEXT,
    row_count  INT,
    followups  TEXT,
    expires_at BIGINT,
    hit_count  INT DEFAULT 0
);

-- Loaded files tracking
CREATE TABLE IF NOT EXISTS _loaded_files (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    filepath      VARCHAR(500),
    table_name    VARCHAR(200),
    row_count     INT,
    loaded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_modified FLOAT
);

-- Relationships cache
CREATE TABLE IF NOT EXISTS _relationships (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    from_table   VARCHAR(200),
    from_col     VARCHAR(200),
    to_table     VARCHAR(200),
    to_col       VARCHAR(200),
    description  TEXT,
    confidence   VARCHAR(20),
    detected_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log
CREATE TABLE IF NOT EXISTS _audit_log (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT,
    username       VARCHAR(100),
    user_role      VARCHAR(50),
    query_type     VARCHAR(50),
    tables_used    TEXT,
    row_count      INT,
    response_ms    INT,
    status         VARCHAR(20),
    blocked_reason TEXT,
    intent         VARCHAR(50),
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sync sources
CREATE TABLE IF NOT EXISTS _sync_sources (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    source_name   VARCHAR(200) NOT NULL,
    source_type   VARCHAR(50) NOT NULL,
    table_name    VARCHAR(200) NOT NULL,
    source_url    TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    sync_interval INT DEFAULT 300,
    last_sync     TIMESTAMP NULL,
    last_status   VARCHAR(50) DEFAULT 'pending',
    last_row_count INT DEFAULT 0,
    error_message TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sync log
CREATE TABLE IF NOT EXISTS _sync_log (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    source_id    INT,
    source_name  VARCHAR(200),
    rows_added   INT DEFAULT 0,
    rows_updated INT DEFAULT 0,
    status       VARCHAR(50),
    error        TEXT,
    duration_ms  INT,
    synced_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Webhook log
CREATE TABLE IF NOT EXISTS _webhook_log (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    source_name   VARCHAR(200),
    table_name    VARCHAR(200),
    rows_received INT DEFAULT 0,
    ip_address    VARCHAR(50),
    status        VARCHAR(50),
    received_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);