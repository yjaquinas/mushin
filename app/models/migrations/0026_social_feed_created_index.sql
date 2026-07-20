CREATE INDEX IF NOT EXISTS idx_entry_visible_created
    ON entry (julianday(created_at) DESC, id DESC)
    WHERE hidden_at IS NULL;
