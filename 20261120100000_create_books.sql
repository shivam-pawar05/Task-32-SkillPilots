CREATE TABLE IF NOT EXISTS books (
    book_id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    author_id BIGINT REFERENCES authors(author_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
