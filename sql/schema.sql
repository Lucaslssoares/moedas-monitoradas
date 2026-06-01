-- price_history: histórico de preços por produto
CREATE TABLE IF NOT EXISTS price_history (
    id               SERIAL PRIMARY KEY,
    product_id       VARCHAR(60)     NOT NULL,
    product_title    TEXT,
    seller_id        BIGINT,
    seller_nickname  VARCHAR(120),
    price            NUMERIC(12, 2)  NOT NULL,
    original_price   NUMERIC(12, 2),
    currency_id      VARCHAR(10)     DEFAULT 'BRL',
    permalink        TEXT,
    searched_at      TIMESTAMPTZ     DEFAULT NOW(),
    variation_pct    NUMERIC(10, 4),
    alerted          BOOLEAN         DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_ph_product_id   ON price_history (product_id);
CREATE INDEX IF NOT EXISTS idx_ph_searched_at  ON price_history (searched_at DESC);
CREATE INDEX IF NOT EXISTS idx_ph_alerted      ON price_history (alerted) WHERE alerted = TRUE;
