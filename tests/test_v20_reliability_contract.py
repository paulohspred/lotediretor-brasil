from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def compact(path: str) -> str:
    return re.sub(r"\s+", " ", (ROOT / path).read_text(encoding="utf-8")).lower()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


idem = compact("services/platform-api/src/common/idempotency.ts")
require("on conflict (tenant_id,scope,idempotency_key) do update" in idem,
        "idempotency must atomically reclaim an expired primary-key row")
require("where api.idempotency_key.expires_at<=now()" in idem,
        "idempotency reclaim must be restricted to expired rows")
require("set status='in_progress',response=null,created_at=now(),completed_at=null" in idem,
        "reclaimed idempotency rows must not replay stale completion data")
require("status==='completed'" in idem and "replayed:true" in idem,
        "active completed commands must still replay their stored result")
require("idempotency_ttl_hours" in idem,
        "idempotency TTL must be explicit and bounded")

outbox = compact("services/event-dispatcher/src/main.ts")
require("status='publishing' and (lease_until is null or lease_until<=now())" in outbox,
        "dispatcher must reclaim stale/legacy PUBLISHING rows")
require("claimed_by=$2,claimed_at=now(),lease_until=now()" in outbox,
        "dispatcher claims must record ownership and a finite lease")
require("where id=$1 and status='publishing' and claimed_by=$3" in outbox,
        "successful publication must only be finalized by the current claim owner")
require("where id=$1 and status='publishing' and claimed_by=$4" in outbox,
        "failed publication must only be finalized by the current claim owner")
require("const bus=await eventbus(); const rows=await claimbatch();" in outbox,
        "NATS must be available before DB work is claimed")
require("msgid:string(row.id)" in outbox,
        "JetStream publication must preserve the outbox id as duplicate-suppression id")

migration = compact("db/platform/migrations/215_v20_reliability_outbox_lease.sql")
for column in ("claimed_by", "claimed_at", "lease_until"):
    require(f"add column if not exists {column}" in migration,
            f"migration 215 must add {column}")
require("where status='publishing' and lease_until is null" in migration,
        "migration must make pre-upgrade stuck publications immediately reclaimable")
require("event_outbox_publish_lease_idx" in migration,
        "stale publication lookup must be indexed")

print("v20 reliability contracts: OK")
