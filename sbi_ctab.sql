CREATE TABLE sbi_portfolio (
    log_date DATE PRIMARY KEY,
    usdrate NUMERIC(6,2),
    total_amount_jpy NUMERIC(18,0),
    total_amount_usd NUMERIC(20,2)
);
CREATE TABLE sbi_portfolio_detail (
    log_date DATE,
    brand TEXT,
    brand_price_usd NUMERIC(20,2),
    amount_jpy NUMERIC(18,0),
    amount_jpy_delta NUMERIC(18,0),
    amount_usd NUMERIC(20,2),
    amount_usd_delta NUMERIC(20,2),
    PRIMARY KEY (log_date, brand)
);
