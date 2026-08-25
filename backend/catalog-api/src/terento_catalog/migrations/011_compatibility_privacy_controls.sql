ALTER TABLE compatibility_evidence_event
    ADD COLUMN deletion_token_hash TEXT;

-- Earlier beta events have no user-held deletion credential. Remove them
-- instead of retaining reports that the revised client cannot erase.
DELETE FROM compatibility_evidence_event
    WHERE deletion_token_hash IS NULL;

ALTER TABLE compatibility_evidence_event
    ALTER COLUMN deletion_token_hash SET NOT NULL;

CREATE INDEX compatibility_evidence_received_idx
    ON compatibility_evidence_event(received_at);

DROP TABLE compatibility_evidence_confirmation;

ALTER TABLE compatibility_evidence_event
    DROP COLUMN raw_event;
