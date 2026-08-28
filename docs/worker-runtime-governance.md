# Worker Runtime Governance

## Purpose

This document defines the single-source rules for external worker state, credentials, protocol capabilities, administration status, and runtime paths.

The DSM backend remains authoritative. External workers execute compatible jobs but do not own package state, status semantics, authentication policy, queue state, model consent, or final writes.

## Canonical services

```text
WorkerRuntimePathService
  owns package-var and SQLite runtime database path resolution

WorkerStateStore
  owns state schema, atomic persistence and locking

WorkerCredentialService
  owns token issuance, hashing, scopes, revocation checks and worker binding

WorkerProtocol
  owns capability names, job-type mapping, token scopes and schema version

WorkerApiService
  owns worker registration, heartbeat, queue lifecycle and worker/admin status

WorkerProvisioningService
  owns enrollment and model distribution, using the same state and credentials
```

No API router, CLI helper, installation script, or feature service may independently parse or write worker runtime tables, hash worker tokens, infer enrollment status, or define a second capability list.

## Runtime persistence

The package-local SQLite database is the authoritative worker runtime store:

```text
<SYNOPKG_PKGVAR>/imgdata.sqlite3
```

`worker-api-state.json` is not a runtime source. The backend does not import it, merge it, or use it as a fallback.

## State schema

Current schema version: `2`.

Required runtime domains:

```text
tokens
workers
jobs
enrollments
```

`WorkerStateStore` persists those domains in SQLite worker tables and preserves unknown top-level fields in app state when callers write them through the store. Missing worker tables are initialized as an empty state. Invalid stored JSON, invalid structure, read failures, and write failures are distinct errors and must not be rendered as an empty installation.

All mutations go through the store. Runtime permissions and database initialization are owned by the database layer, not repaired by individual callers.

Completed jobs are queue transport, not history. They are deleted after the backend consumes the result. Failed, cancelled, expired jobs and used or expired enrollments are pruned from runtime state after their short retention window.

## Credentials

All tokens use the same entry contract:

```text
token_hash
created_at
revoked
worker_id
scopes
issued_via
enrollment_id
```

A bound token cannot be used by another worker. Every protected operation requires an explicit scope.

Enrollment redemption writes the token and marks the enrollment used in one state transaction.

## Worker lifecycle

Registration is explicit. Heartbeat updates an existing registration and must not silently create a second registration path.

Registration owns:

```text
worker_id
version
capabilities
metadata
registered_at
last_seen_at
status
```

Heartbeat may update presence, status, capabilities, and metadata while preserving registration identity and version.

## Capabilities and job types

`WorkerProtocol` is the Python authority for supported capability names and their job-type mapping. Queue claims compare job types against the mapped supported job types, not against an unrelated free-form list.

Unknown capability and job-type names are rejected or ignored according to the service contract. New commands require one protocol change plus corresponding worker and contract tests.

## Status ownership

The backend owns status semantics as defined by `status-concept-integrated.md`.

Worker runtime status and administration status include a schema version and component identity. API routers only authenticate, validate HTTP input, and render service output. They must not reconstruct enrollment phases, worker readiness, counters, or secret masking from raw state.

Secrets such as enrollment hashes and token hashes are never included in administration status.

## Testing requirements

Changes to worker runtime infrastructure require:

- service-level unit tests for behavior and error codes;
- migration tests for older state schemas;
- scope and worker-binding tests;
- path-priority tests;
- registration and heartbeat lifecycle tests;
- capability/job mapping tests;
- administration status tests;
- concurrency and transaction rollback tests for security- and queue-sensitive transitions;
- static architecture contract tests preventing duplicate state, credential, status, path, permission, enrollment and queue logic.
