CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    points INT DEFAULT 0,
    is_verified BOOLEAN DEFAULT FALSE,
    referrals INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
