CREATE TABLE wn_portfolio (
    log_date DATE PRIMARY KEY,
    usdrate NUMERIC(6,2),
    total_amount_jpy NUMERIC(18,0),
    total_amount_usd NUMERIC(20,2),
    total_deposit_jpy NUMERIC(18,0),
    total_withdraw_jpy NUMERIC(18,0)
);

CREATE TABLE wn_portfolio_detail (
    log_date TEXT,
    brand TEXT,
    amount_jpy NUMERIC,
    amount_jpy_delta NUMERIC,
    amount_usd NUMERIC,
    amount_usd_delta NUMERIC,
    price_usd NUMERIC,
    qty NUMERIC,
    PRIMARY KEY (log_date, brand)
);

CREATE TABLE wn_history (
    start_date TEXT,
    end_date TEXT,
    history_type TEXT,
    total_jpy NUMERIC,
    usdrate NUMERIC,
    PRIMARY KEY (start_date, history_type)
);

CREATE TABLE wn_history_detail (
    start_date TEXT,
    history_type TEXT,
    trade_type TEXT,
    brand TEXT,
    brand_price_usd NUMERIC,
    trade_qty NUMERIC,
    trade_jpy NUMERIC,
    trade_usd NUMERIC,
    PRIMARY KEY (start_date, history_type, trade_type, brand)
);
