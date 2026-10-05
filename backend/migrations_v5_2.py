"""Additive V5.2 provider provenance and directory review tables."""

MIGRATION_24 = """
BEGIN;

CREATE TABLE provider_source_registry (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    provider_authority TEXT NOT NULL,
    source_url TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    license_type TEXT NOT NULL,
    reuse_allowed INTEGER NOT NULL CHECK(reuse_allowed IN (0,1)),
    scope TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    update_cycle TEXT NOT NULL,
    downloaded_at TEXT,
    schema_version TEXT NOT NULL,
    ingestion_status TEXT NOT NULL CHECK(ingestion_status IN
        ('DISCOVERED','LICENSE_VERIFIED','INGEST_ALLOWED','INGEST_BLOCKED','INGESTED',
         'SCHEMA_DRIFT','ERROR')),
    last_success TEXT,
    last_error TEXT,
    content_hash TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_provider_sources_status ON provider_source_registry(ingestion_status, source_id);

CREATE TABLE provider_directory_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES provider_source_registry(source_id),
    raw_file_hash TEXT NOT NULL CHECK(length(raw_file_hash)=64),
    source_snapshot_date TEXT NOT NULL,
    downloaded_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    schema_hash TEXT NOT NULL CHECK(length(schema_hash)=64),
    row_count INTEGER NOT NULL CHECK(row_count >= 0),
    normalized_snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_id, raw_file_hash)
);
CREATE INDEX idx_provider_snapshots_source_date
    ON provider_directory_snapshots(source_id, source_snapshot_date DESC, created_at DESC);
CREATE TRIGGER trg_provider_snapshot_no_update
BEFORE UPDATE ON provider_directory_snapshots
BEGIN
    SELECT RAISE(ABORT, 'PROVIDER_SNAPSHOT_IMMUTABLE');
END;
CREATE TRIGGER trg_provider_snapshot_no_delete
BEFORE DELETE ON provider_directory_snapshots
BEGIN
    SELECT RAISE(ABORT, 'PROVIDER_SNAPSHOT_IMMUTABLE');
END;

ALTER TABLE provider_directory_entries RENAME TO provider_directory_entries_v23;
CREATE TABLE provider_directory_entries (
    entry_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
    service_hint TEXT,
    region_id TEXT NOT NULL DEFAULT '',
    existence_provenance TEXT NOT NULL
        CHECK(existence_provenance IN (
            'REAL_DIRECTORY', 'SELF_REPORTED', 'LOCAL_AUTHORITY_VERIFIED',
            'SIMULATED', 'UNKNOWN'
        )),
    reference_date TEXT,
    linked_provider_id TEXT REFERENCES providers(provider_id),
    created_at TEXT NOT NULL,
    public_address TEXT,
    source_record_id TEXT,
    region_label TEXT NOT NULL DEFAULT '',
    region_code TEXT,
    normalized_name TEXT,
    organization_type TEXT NOT NULL DEFAULT 'UNKNOWN',
    latitude REAL CHECK(latitude IS NULL OR latitude BETWEEN -90 AND 90),
    longitude REAL CHECK(longitude IS NULL OR longitude BETWEEN -180 AND 180),
    public_service_description TEXT,
    public_contact_available INTEGER NOT NULL DEFAULT 0
        CHECK(public_contact_available IN (0,1)),
    active_status_if_available TEXT,
    snapshot_id TEXT REFERENCES provider_directory_snapshots(snapshot_id),
    UNIQUE(source_id, snapshot_id, source_record_id)
);
INSERT INTO provider_directory_entries(
    entry_id, source_id, name, service_hint, region_id, existence_provenance,
    reference_date, linked_provider_id, created_at, public_address
)
SELECT entry_id, source_id, name, service_hint, region_id, existence_provenance,
       reference_date, linked_provider_id, created_at, public_address
FROM provider_directory_entries_v23;
DROP TABLE provider_directory_entries_v23;
CREATE INDEX idx_provider_directory_region ON provider_directory_entries(region_id);
CREATE INDEX idx_provider_directory_source_snapshot
    ON provider_directory_entries(source_id, snapshot_id);
CREATE INDEX idx_provider_directory_name ON provider_directory_entries(normalized_name);
CREATE INDEX idx_provider_directory_type_region
    ON provider_directory_entries(organization_type, region_id);

CREATE TABLE provider_duplicate_candidates (
    candidate_id TEXT PRIMARY KEY,
    entry_id_a TEXT NOT NULL REFERENCES provider_directory_entries(entry_id),
    entry_id_b TEXT NOT NULL REFERENCES provider_directory_entries(entry_id),
    match_signals_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'POSSIBLE_DUPLICATE' CHECK(status IN
        ('POSSIBLE_DUPLICATE','CONFIRMED_SAME','CONFIRMED_DISTINCT')),
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    CHECK(entry_id_a < entry_id_b),
    UNIQUE(entry_id_a, entry_id_b)
);
CREATE INDEX idx_provider_duplicate_review
    ON provider_duplicate_candidates(status, created_at DESC);

CREATE TABLE provider_service_mapping_reviews (
    mapping_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES provider_directory_entries(entry_id),
    source_description TEXT NOT NULL,
    suggested_service_type TEXT REFERENCES service_types(service_type_id),
    status TEXT NOT NULL CHECK(status IN
        ('UNMAPPED','MAPPING_SUGGESTED','VERIFIED_MAPPING','REJECTED_MAPPING')),
    regulation_level TEXT NOT NULL CHECK(regulation_level IN
        ('UNREGULATED','LIMITED','LICENSE_REQUIRED','EXCLUDED')),
    review_note TEXT,
    provenance TEXT NOT NULL DEFAULT 'REAL_DIRECTORY',
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(entry_id, suggested_service_type)
);
CREATE INDEX idx_provider_mapping_review ON provider_service_mapping_reviews(status, entry_id);

COMMIT;
"""

MIGRATION_25 = """
BEGIN;
CREATE TABLE pilot_import_batches (
    batch_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    template_type TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    validated_at TEXT NOT NULL,
    confirmed_at TEXT,
    rows_total INTEGER NOT NULL CHECK(rows_total >= 0),
    rows_valid INTEGER NOT NULL DEFAULT 0 CHECK(rows_valid >= 0),
    rows_warning INTEGER NOT NULL DEFAULT 0 CHECK(rows_warning >= 0),
    rows_error INTEGER NOT NULL DEFAULT 0 CHECK(rows_error >= 0),
    rows_imported INTEGER NOT NULL DEFAULT 0 CHECK(rows_imported >= 0),
    status TEXT NOT NULL CHECK(status IN ('PREVIEWED','IMPORTED','IMPORTED_WITH_ERRORS')),
    source_type TEXT NOT NULL,
    snapshot_id TEXT,
    UNIQUE(template_type, content_sha256)
);
CREATE INDEX idx_pilot_import_batches_status
    ON pilot_import_batches(status, uploaded_at DESC);

CREATE TABLE pilot_import_rows (
    row_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES pilot_import_batches(batch_id) ON DELETE CASCADE,
    template_type TEXT NOT NULL,
    row_number INTEGER NOT NULL CHECK(row_number >= 2),
    row_fingerprint TEXT NOT NULL CHECK(length(row_fingerprint)=64),
    status TEXT NOT NULL CHECK(status IN ('VALID','WARNING','ERROR')),
    normalized_json TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    imported_record_id TEXT,
    UNIQUE(batch_id, row_number)
);
CREATE INDEX idx_pilot_import_rows_batch_status
    ON pilot_import_rows(batch_id, status, row_number);

CREATE TABLE pilot_import_records (
    record_id TEXT PRIMARY KEY,
    template_type TEXT NOT NULL,
    row_fingerprint TEXT NOT NULL CHECK(length(row_fingerprint)=64),
    source_type TEXT NOT NULL,
    provenance TEXT NOT NULL,
    normalized_json TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    batch_id TEXT NOT NULL REFERENCES pilot_import_batches(batch_id),
    row_number INTEGER NOT NULL,
    UNIQUE(template_type, row_fingerprint)
);
CREATE INDEX idx_pilot_import_records_template_time
    ON pilot_import_records(template_type, imported_at DESC);
CREATE INDEX idx_pilot_import_records_source
    ON pilot_import_records(source_type, template_type);
COMMIT;
"""
