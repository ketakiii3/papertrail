-- F2: dedupe key for Form 4 rows = (accession_number, line_no).
-- F3: keep the raw Form 4 transaction code and the A/D flag; transaction_type
--     becomes buy (P) / sell (S) / other (everything else).
ALTER TABLE insider_transactions
  ADD COLUMN IF NOT EXISTS accession_number VARCHAR(25),
  ADD COLUMN IF NOT EXISTS line_no INT,
  ADD COLUMN IF NOT EXISTS transaction_code VARCHAR(2),
  ADD COLUMN IF NOT EXISTS acquired_disposed CHAR(1);

-- Fractional shares (dividend reinvestment etc.) don't fit BIGINT.
ALTER TABLE insider_transactions ALTER COLUMN shares TYPE NUMERIC(18,4);

-- Rows seeded by hand used the raw code as the type ('P' / 'S').
UPDATE insider_transactions
SET transaction_code = UPPER(transaction_type),
    transaction_type = CASE UPPER(transaction_type) WHEN 'P' THEN 'buy' ELSE 'sell' END
WHERE accession_number IS NULL AND UPPER(transaction_type) IN ('P', 'S');

-- Dedupe legacy rows that have no accession number. Deleting a transaction
-- cascades to its surveillance_flags row, which is what we want for duplicates.
DELETE FROM insider_transactions t USING insider_transactions u
WHERE t.id > u.id
  AND t.accession_number IS NULL AND u.accession_number IS NULL
  AND t.company_id = u.company_id AND t.insider_name = u.insider_name
  AND t.transaction_date = u.transaction_date AND t.transaction_type = u.transaction_type
  AND t.shares IS NOT DISTINCT FROM u.shares AND t.price IS NOT DISTINCT FROM u.price;

CREATE UNIQUE INDEX IF NOT EXISTS uq_insider_txn_line
  ON insider_transactions (accession_number, line_no)
  WHERE accession_number IS NOT NULL;
