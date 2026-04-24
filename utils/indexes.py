from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import OperationFailure
from database import get_database


async def _safe_create_indexes(collection, indexes: list, label: str) -> None:
    """Create indexes for a collection, skipping any that already exist with
    conflicting options instead of crashing the entire startup."""
    try:
        await collection.create_indexes(indexes)
        print(f"[DB] Indexes OK: {label}")
    except OperationFailure as exc:
        # Code 85 = IndexOptionsConflict, 86 = IndexKeySpecsConflict
        if exc.code in (85, 86):
            print(f"[DB] Index conflict on '{label}' (already exists with different options) — skipping: {exc.details.get('errmsg', exc)}")
            # Fall back to creating indexes one-by-one so non-conflicting ones still land
            for idx in indexes:
                try:
                    await collection.create_indexes([idx])
                except OperationFailure as inner:
                    if inner.code in (85, 86):
                        print(f"[DB]   Skipped conflicting index on '{label}': {inner.details.get('errmsg', inner)}")
                    else:
                        raise
        else:
            raise


async def create_indexes() -> None:
    db = get_database()

    # ── responses ─────────────────────────────────────────────────────────────
    await _safe_create_indexes(db["responses"], [
        IndexModel([("session_id", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel([("submitted_at", DESCENDING)]),
        IndexModel([("assigned_examiner_email", ASCENDING)]),
        IndexModel([("candidate_account_id", ASCENDING)]),
        IndexModel([("form_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("session_id", ASCENDING), ("email", ASCENDING)]),
        IndexModel([("status", ASCENDING), ("submitted_at", DESCENDING)]),
        IndexModel([("answers.Certification souhaitée", ASCENDING), ("status", ASCENDING)]),
    ], "responses")

    # ── sessions ───────────────────────────────────────────────────────────────
    await _safe_create_indexes(db["sessions"], [
        IndexModel([("status", ASCENDING)]),
        IndexModel([("sequence_number", ASCENDING)]),
    ], "sessions")

    # ── candidate_accounts ────────────────────────────────────────────────────
    # Note: omit sparse=True — if the collection already has a non-sparse unique
    # index on email the options must match exactly to avoid a conflict error.
    await _safe_create_indexes(db["candidate_accounts"], [
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("public_id", ASCENDING)]),
    ], "candidate_accounts")

    # ── audit_logs ─────────────────────────────────────────────────────────────
    await _safe_create_indexes(db["audit_logs"], [
        IndexModel([("timestamp", DESCENDING)]),
        IndexModel([("action", ASCENDING), ("timestamp", DESCENDING)]),
        IndexModel([("user_email", ASCENDING), ("timestamp", DESCENDING)]),
        IndexModel([("resource_type", ASCENDING), ("timestamp", DESCENDING)]),
    ], "audit_logs")

    # ── exams ──────────────────────────────────────────────────────────────────
    await _safe_create_indexes(db["exams"], [
        IndexModel([("certification", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ], "exams")

    # ── forms ──────────────────────────────────────────────────────────────────
    await _safe_create_indexes(db["forms"], [
        IndexModel([("title", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
    ], "forms")

    # ── users ──────────────────────────────────────────────────────────────────
    # Match the existing index options exactly (unique=True, no sparse) to avoid
    # IndexKeySpecsConflict (error 86) on an already-running database.
    await _safe_create_indexes(db["users"], [
        IndexModel([("email", ASCENDING)], unique=True),
    ], "users")

    print("[DB] All indexes created/verified.")
