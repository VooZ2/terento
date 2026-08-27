CREATE TABLE public_compatibility_review_audit (
    id BIGSERIAL PRIMARY KEY,
    device_model_id TEXT NOT NULL REFERENCES device_model(id) ON DELETE RESTRICT,
    compatibility_identity TEXT NOT NULL,
    previous_review_status TEXT,
    new_review_status TEXT NOT NULL,
    previous_public_statistics_enabled BOOLEAN,
    new_public_statistics_enabled BOOLEAN NOT NULL,
    public_display_name TEXT NOT NULL,
    note TEXT,
    changed_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (new_review_status IN ('PENDING', 'APPROVED', 'REJECTED'))
);

CREATE INDEX public_compatibility_review_audit_device_idx
    ON public_compatibility_review_audit(device_model_id, changed_at DESC);
