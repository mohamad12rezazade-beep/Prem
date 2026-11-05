CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    points INT DEFAULT 0,
    is_verified BOOLEAN DEFAULT FALSE,
    referrals INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS force_channels (
    id SERIAL PRIMARY KEY,
    channel_username VARCHAR(255) UNIQUE NOT NULL
);

-- اضافه کردن چنل‌های اولیه
INSERT INTO force_channels (channel_username) VALUES ('@Poneix') ON CONFLICT DO NOTHING;
INSERT INTO force_channels (channel_username) VALUES ('@BET_1XZX') ON CONFLICT DO NOTHING;
