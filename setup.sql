CREATE DATABASE IF NOT EXISTS chatbot_db;
USE chatbot_db;

CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(50) DEFAULT 'viewer',
    allowed_tables TEXT DEFAULT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    role       VARCHAR(20) NOT NULL,
    message    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roles (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    can_upload  BOOLEAN DEFAULT FALSE,
    can_query   BOOLEAN DEFAULT TRUE,
    is_admin    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT IGNORE INTO roles
(name, description, can_upload, can_query, is_admin)
VALUES
('admin',   'Full access',           TRUE,  TRUE, TRUE),
('analyst', 'Query + upload access', TRUE,  TRUE, FALSE),
('viewer',  'Read only access',      FALSE, TRUE, FALSE);