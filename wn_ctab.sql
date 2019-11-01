CREATE TABLE wn_portfolio (
    log_date DATE PRIMARY KEY,
    usdrate NUMERIC(6,2),
    total_amount_jpy NUMERIC(18,0),
    total_amount_usd NUMERIC(20,2),
    total_deposit_jpy NUMERIC(18,0),
    total_withdraw_jpy NUMERIC(18,0)
);

CREATE TABLE wn_portfolio_detail (
    log_date DATE,
    brand TEXT,
    amount_jpy NUMERIC(18,0),
    amount_jpy_delta NUMERIC(18,0),
    amount_usd NUMERIC(20,2),
    amount_usd_delta NUMERIC(20,2),
    PRIMARY KEY (log_date, brand)
);

CREATE TABLE wn_history (
    start_date DATE,
    end_date DATE,
    history_type TEXT,
    total_jpy NUMERIC(20,0),
    usdrate NUMERIC(6,2),
    PRIMARY KEY (start_date, history_type)
);

CREATE TABLE wn_history_detail (
    start_date DATE,
    history_type TEXT,
    trade_type TEXT,
    brand TEXT,
    brand_price_usd NUMERIC(20,2),
    trade_qty NUMERIC(20,3),
    trade_jpy NUMERIC(20,0),
    trade_usd NUMERIC(20,2),
    PRIMARY KEY (start_date, history_type, trade_type, brand)
);
