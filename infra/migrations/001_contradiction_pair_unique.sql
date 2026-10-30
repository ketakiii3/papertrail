-- F1: one row per unordered claim pair. Kafka redelivery and out-of-order
-- backfills used to store the same pair more than once.
DELETE FROM contradictions c USING contradictions d
WHERE c.id > d.id
  AND LEAST(c.claim_a_id, c.claim_b_id)    = LEAST(d.claim_a_id, d.claim_b_id)
  AND GREATEST(c.claim_a_id, c.claim_b_id) = GREATEST(d.claim_a_id, d.claim_b_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_pair
  ON contradictions ((LEAST(claim_a_id, claim_b_id)), (GREATEST(claim_a_id, claim_b_id)));
