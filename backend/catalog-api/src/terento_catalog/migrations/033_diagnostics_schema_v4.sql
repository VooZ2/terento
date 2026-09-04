-- Schema v4 deliberately has no deletion credential. Retain all events and
-- legacy token hashes; the public API remains immutable.
ALTER TABLE compatibility_evidence_event
    ALTER COLUMN deletion_token_hash DROP NOT NULL;
