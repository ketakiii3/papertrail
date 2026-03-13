-- PaperTrail PostgreSQL Schema
CREATE EXTENSION IF NOT EXISTS vector;

-- Companies table (S&P 500)
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) UNIQUE NOT NULL,
    name TEXT NOT NULL,
    cik VARCHAR(10) UNIQUE NOT NULL,
    sector TEXT,
    industry TEXT,
    sp500 BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- SEC Filings
CREATE TABLE IF NOT EXISTS filings (
    id SERIAL PRIMARY KEY,
    company_id INT REFERENCES companies(id) ON DELETE CASCADE,
    accession_number VARCHAR(25) UNIQUE NOT NULL,
    form_type VARCHAR(10) NOT NULL,
    filed_at DATE NOT NULL,
    period_of_report DATE,
    url TEXT NOT NULL,
    raw_text TEXT,
    processed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_filings_company ON filings(company_id, filed_at DESC);
CREATE INDEX IF NOT EXISTS idx_filings_type ON filings(form_type, filed_at DESC);

-- Extracted Claims
CREATE TABLE IF NOT EXISTS claims (
    id SERIAL PRIMARY KEY,
    filing_id INT REFERENCES filings(id) ON DELETE CASCADE,
    company_id INT REFERENCES companies(id) ON DELETE CASCADE,
    speaker TEXT,
    claim_text TEXT NOT NULL,
    claim_type VARCHAR(50),
    topic VARCHAR(100),
    sentiment VARCHAR(10),
    confidence FLOAT,
    entities JSONB DEFAULT '{}',
    temporal_ref TEXT,
    source_section TEXT,
    embedding vector(384),
    claim_date DATE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_claims_company ON claims(company_id, claim_date DESC);
CREATE INDEX IF NOT EXISTS idx_claims_filing ON claims(filing_id);
CREATE INDEX IF NOT EXISTS idx_claims_type ON claims(claim_type);

-- Contradictions
CREATE TABLE IF NOT EXISTS contradictions (
    id SERIAL PRIMARY KEY,
    claim_a_id INT REFERENCES claims(id) ON DELETE CASCADE,
    claim_b_id INT REFERENCES claims(id) ON DELETE CASCADE,
    company_id INT REFERENCES companies(id) ON DELETE CASCADE,
    similarity_score FLOAT NOT NULL,
    nli_contradiction_score FLOAT NOT NULL,
    severity VARCHAR(10) NOT NULL DEFAULT 'low',
    time_gap_days INT,
    explanation TEXT,
    agent_reasoning TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_contradictions_company ON contradictions(company_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_contradictions_severity ON contradictions(severity, created_at DESC);

-- Insider Transactions (Form 4)
CREATE TABLE IF NOT EXISTS insider_transactions (
    id SERIAL PRIMARY KEY,
    company_id INT REFERENCES companies(id) ON DELETE CASCADE,
    insider_name TEXT NOT NULL,
    insider_title TEXT,
    transaction_type VARCHAR(10) NOT NULL,
    shares BIGINT,
    price DECIMAL(12,2),
    total_value DECIMAL(15,2),
    transaction_date DATE NOT NULL,
    filing_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_insider_company ON insider_transactions(company_id, transaction_date DESC);

-- Watchlist (simple, no auth for MVP)
CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    email TEXT,
    ticker VARCHAR(10) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(email, ticker)
);
