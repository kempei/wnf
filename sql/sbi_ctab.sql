CREATE TABLE sbi_portfolio (
    log_date TEXT PRIMARY KEY,
    usdrate NUMERIC,
    total_amount_jpy NUMERIC,
    total_amount_usd NUMERIC,
    inv_capacity_jpy NUMERIC
);
CREATE TABLE sbi_portfolio_detail (
    log_date TEXT,
    brand TEXT,
    price_usd NUMERIC,
    qty NUMERIC,
    amount_jpy NUMERIC,
    amount_jpy_delta NUMERIC,
    amount_usd NUMERIC,
    amount_usd_delta NUMERIC,
    PRIMARY KEY (log_date, brand)
);
