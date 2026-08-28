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

## Worker Runtime Hardening

### Meaning

Worker Runtime Hardening means reducing the worker runtime to one authoritative persistence source and one controlled service path for every security- and queue-relevant state transition.

The target architecture is:

```text
API / CLI / provisioning / feature code
        |
        v
canonical worker services
        |
        v
WorkerStateStore
        |
        v
<SYNOPKG_PKGVAR>/imgdata.sqlite3
```

There must be no second writable runtime source and no parallel implementation for tokens, enrollments, workers, jobs, capabilities, permissions, or runtime status.

Hardening is not primarily a database migration. The important part is ownership: callers request an operation from the canonical service instead of reading state, modifying a dictionary/table/file themselves and writing it back.

### Why this matters

A worker runtime contains security-sensitive and concurrency-sensitive data:

- authentication tokens and revocation state;
- worker identity and binding;
- enrollment codes and their one-time lifecycle;
- queue ownership and job transitions;
- result consumption state;
- worker heartbeat/readiness information;
- protocol capabilities and authorization scopes.

If more than one component owns these rules, the same logical state can be interpreted or changed differently depending on the code path. This creates failure modes that are difficult to diagnose and potentially security-relevant.

### Benefits

1. **Single source of truth**  
   Runtime state cannot diverge between SQLite, JSON files, process memory, CLI-specific storage, or feature-specific caches.

2. **Atomic state transitions**  
   Operations such as enrollment redemption, token creation, claim, completion and result consumption can be performed under the same transaction/locking model.

3. **Consistent security policy**  
   Token hashing, scope checks, worker binding and revocation are implemented once and cannot silently differ between API, CLI and provisioning paths.

4. **Predictable recovery**  
   Restarting the DSM backend reconstructs authoritative runtime state from SQLite instead of deciding which of several state sources is newest or valid.

5. **No stale fallback state**  
   A deleted/revoked token, consumed job or used enrollment cannot reappear through an old JSON fallback or an independently maintained cache.

6. **Clear ownership and debugging**  
   Every mutation has one service owner. Failures can be traced to a defined boundary instead of searching several state implementations.

7. **Safer concurrency**  
   Claim, heartbeat, enrollment and result operations use common locks/transactions and do not race through unrelated read-modify-write implementations.

8. **Simpler migrations**  
   Future schema changes are concentrated in the database/store layer instead of requiring coordinated migration logic in routers, scripts and feature services.

9. **Testable architecture**  
   Static tests can prevent new direct database/file access and service tests can verify the complete state transition contract.

10. **Preparation for higher worker load**  
    A future central pipeline or multiple workers can rely on deterministic queue semantics instead of amplifying existing split-brain state problems.

## Hardening Worklist

The following list is the required work plan. A point is complete only when production code and tests both enforce the target behavior.

### 1. Inventory all runtime state access

- [ ] Search production code for `worker-api-state.json` and every former worker runtime JSON filename.
- [ ] Search for direct access to SQLite worker tables (`worker_tokens`, `worker_workers`, `worker_jobs`, `worker_enrollments`).
- [ ] Search for direct reads/writes of `tokens`, `workers`, `jobs`, and `enrollments` outside canonical services.
- [ ] Search for independent token hashing, scope parsing, revocation checks and worker-binding logic.
- [ ] Search for independent enrollment-code creation, validation, expiry or redemption logic.
- [ ] Search for independent job lifecycle transitions (`queued`, `claimed`, `completed`, `failed`, `cancelled`, `expired`).
- [ ] Search CLI tools, test helpers, installation/update scripts and development routers separately; these often retain old state paths after backend migration.
- [ ] Classify every result as canonical, read-only diagnostic, migration-only, test-only, or forbidden runtime access.

**Acceptance:** every production runtime access point is known and assigned to one canonical owner.

### 2. Enforce SQLite as the only runtime source

- [ ] Confirm `WorkerRuntimePathService.database_path()` is the only production resolution path for the worker runtime database.
- [ ] Remove any runtime read fallback to worker JSON state files.
- [ ] Remove any runtime write path to worker JSON state files.
- [ ] Remove merge/import-on-start behavior from legacy state files unless implemented as an explicit one-time migration.
- [ ] If a one-time migration is still needed, make it deterministic, versioned, idempotent and explicitly completed; the legacy source must not remain active afterward.
- [ ] Ensure missing SQLite worker tables initialize through the database migration/schema layer rather than caller-side repair logic.
- [ ] Ensure database read/parse failures remain errors and are not converted into an apparently empty worker installation.
- [ ] Verify package update/install paths preserve the SQLite runtime database correctly.

**Acceptance:** deleting or modifying any old worker JSON file has no effect on production runtime behavior.

### 3. Harden `WorkerStateStore` ownership

- [ ] Make `WorkerStateStore` the only component allowed to persist worker runtime domains.
- [ ] Ensure direct SQL against worker runtime tables exists only inside the canonical store/database implementation.
- [ ] Ensure all mutations use the store's transaction/locking path.
- [ ] Review `read()`, `write()`, `update()` and `update_if_changed()` for nested locking and transaction consistency.
- [ ] Ensure invalid persisted structures fail with stable error codes instead of being silently normalized where data loss could be hidden.
- [ ] Ensure state schema migration is explicit and covered by tests for every supported previous schema version.
- [ ] Verify runtime database permissions and initialization belong to the database layer only.
- [ ] Prevent feature services from repairing permissions, recreating tables or substituting alternative storage.

**Acceptance:** static architecture tests fail if production code outside the canonical persistence layer directly accesses worker runtime tables.

### 4. Harden token lifecycle through `WorkerCredentialService`

- [ ] Route all token creation through `WorkerCredentialService`.
- [ ] Route hashing through the canonical credential helper only.
- [ ] Route token lookup/validation through the canonical credential service.
- [ ] Route scope normalization and scope checks through the canonical credential/protocol rules.
- [ ] Route token revocation through the canonical service.
- [ ] Enforce worker binding consistently for bound tokens.
- [ ] Ensure comparisons of secret material use the canonical constant-time comparison path where applicable.
- [ ] Verify raw tokens are returned only at issuance/redemption time and are never persisted in plaintext.
- [ ] Ensure token hashes are never returned in normal status/admin API payloads.
- [ ] Remove CLI/API helper code that independently creates token records or hashes values.

**Acceptance:** there is exactly one production implementation for issuance, hashing, validation, scopes, binding and revocation.

### 5. Harden enrollment lifecycle through `WorkerProvisioningService`

- [ ] Route enrollment creation through the provisioning service.
- [ ] Route expiry checks through one implementation.
- [ ] Route redemption through one implementation.
- [ ] Make one-time redemption atomic with worker token issuance.
- [ ] Store `used_at`, worker binding and generated token linkage in the same state transaction.
- [ ] Ensure a used, expired or invalid enrollment can never be redeemed through another API/CLI path.
- [ ] Ensure enrollment secrets/hashes are excluded from status/admin responses.
- [ ] Define and test pruning of used/expired enrollments.
- [ ] Remove duplicate enrollment interpretation from API routers, CLI tools and startup scripts.

**Acceptance:** simultaneous redemption attempts can result in at most one successful enrollment.

### 6. Harden worker registration and heartbeat

- [ ] Route registration through `WorkerApiService` only.
- [ ] Route heartbeat through `WorkerApiService` only.
- [ ] Ensure heartbeat cannot silently create a worker that was never registered.
- [ ] Preserve registration identity and version across heartbeat updates.
- [ ] Validate capability and input-mode advertisement against `WorkerProtocol`.
- [ ] Keep freshness/stale-worker calculation in one service path.
- [ ] Ensure administration status reads normalized service output rather than raw worker records.

**Acceptance:** registration, heartbeat and stale-state behavior are identical regardless of caller/API route.

### 7. Harden job queue lifecycle through `WorkerApiService`

- [ ] Route enqueue through the canonical queue service.
- [ ] Route claim through the canonical queue service.
- [ ] Route result submission through the canonical queue service.
- [ ] Route failure/cancellation/expiry through the canonical queue service.
- [ ] Define legal state transitions centrally and reject illegal transitions.
- [ ] Ensure claim is atomic so two workers cannot successfully claim the same job.
- [ ] Validate claimed job type against the worker's protocol capabilities.
- [ ] Ensure worker identity/token binding is checked before state mutation.
- [ ] Preserve `origin.operation_id`, action and other required job identity fields.
- [ ] Ensure completed result consumption is idempotent.
- [ ] Ensure raw completed jobs are deleted only after normalized result state has been stored successfully.
- [ ] Define and test retention/pruning for failed, cancelled and expired jobs.
- [ ] Remove direct job dictionary/table modifications from processor dispatch, CLI and API helpers.

**Acceptance:** every job transition is performed by one service and has an explicit legal predecessor state.

### 8. Eliminate parallel status construction

- [ ] Ensure worker administration/runtime status is built by canonical backend services.
- [ ] Remove status derivation from raw state in API routers.
- [ ] Remove secret masking implemented independently in multiple callers; status builders should receive only safe data where possible.
- [ ] Ensure schema version and component identity are stable.
- [ ] Keep runtime/administration status separate from global long-running operation progress.

**Acceptance:** routers authenticate/validate/render but do not reconstruct worker runtime semantics.

### 9. Harden protocol ownership

- [ ] Keep capability names in `WorkerProtocol` / generated protocol data only.
- [ ] Keep job-type mapping in the protocol authority only.
- [ ] Keep token scopes in the protocol authority only.
- [ ] Remove duplicated capability arrays or job-type lists from backend callers.
- [ ] Verify worker-side generated protocol definitions match the package release contract.
- [ ] Add static tests rejecting unknown/duplicated production capability definitions.

**Acceptance:** adding a capability requires one protocol contract change and corresponding generated/backend/worker tests, not edits to unrelated capability lists.

### 10. Clean up CLI, development and installation tooling

- [ ] Make CLI tools call canonical services instead of manipulating persisted runtime state directly.
- [ ] Make the development HTTP router call the same service layer as the production router.
- [ ] Remove obsolete state-file utilities or clearly mark migration-only tools so they cannot be used as production runtime sources.
- [ ] Ensure installation/update scripts do not create, merge or repair worker state independently.
- [ ] Ensure worker startup/provisioning scripts interact through the Worker API rather than the DSM runtime database.
- [ ] Ensure external worker code never receives direct filesystem/database access to package runtime state.

**Acceptance:** support tooling cannot create a second runtime behavior that production services do not understand.

### 11. Concurrency and failure testing

- [ ] Test simultaneous job claims from multiple workers.
- [ ] Test simultaneous enrollment redemption.
- [ ] Test heartbeat concurrent with registration/status reads.
- [ ] Test result submission concurrent with timeout/pruning logic.
- [ ] Test token revocation while a worker is active.
- [ ] Test database busy/locked and transaction rollback behavior.
- [ ] Test malformed persisted JSON fields inside SQLite worker records.
- [ ] Test database read failure separately from an empty worker installation.
- [ ] Test process restart with queued, claimed and completed jobs as applicable.
- [ ] Verify no failed transaction leaves a half-created token/enrollment/job transition.

**Acceptance:** security- and queue-relevant multi-record transitions are atomic or fail without partial state.

### 12. Architecture guard tests

Add or maintain static tests that fail when production code introduces:

- [ ] `worker-api-state.json` as a runtime source;
- [ ] direct worker-table SQL outside the canonical persistence/database layer;
- [ ] independent token hashing outside `WorkerCredentialService`;
- [ ] independent enrollment state mutation outside provisioning services;
- [ ] independent queue state mutation outside `WorkerApiService`/canonical queue services;
- [ ] duplicated protocol capability/job/scope lists;
- [ ] worker runtime permission repair outside the database layer;
- [ ] API-router reconstruction of worker status semantics.

**Acceptance:** architectural regressions are caught in CI before review/runtime testing.

### 13. Migration and removal pass

- [ ] Remove dead compatibility code after all production callers use canonical services.
- [ ] Remove obsolete JSON runtime-state documentation and examples.
- [ ] Remove obsolete config entries that select or imply alternate runtime stores.
- [ ] Update worker/admin troubleshooting documentation to reference SQLite/service diagnostics only.
- [ ] Verify package upgrade from the last supported release with existing worker registrations/tokens/jobs as defined by migration policy.
- [ ] Verify fresh installation starts with a valid empty SQLite worker state.

**Acceptance:** there is no dormant alternate runtime implementation left that could later be reactivated accidentally.

### 14. Final hardening acceptance

Worker Runtime Hardening is complete only when all of the following are true:

- [ ] `imgdata.sqlite3` is the only authoritative persisted worker runtime source.
- [ ] No production path reads or writes `worker-api-state.json` or another worker runtime state file.
- [ ] `WorkerStateStore` is the only persistence owner for worker runtime domains.
- [ ] `WorkerCredentialService` is the only token security-policy owner.
- [ ] `WorkerProvisioningService` is the enrollment lifecycle owner.
- [ ] `WorkerApiService` is the worker registration, heartbeat and queue lifecycle owner.
- [ ] `WorkerProtocol` is the capability/job/scope authority.
- [ ] API/CLI/tooling paths use these services rather than reproducing their logic.
- [ ] Concurrency tests demonstrate atomic claim and enrollment behavior.
- [ ] Static architecture tests prevent reintroduction of parallel state/security implementations.
- [ ] Upgrade and fresh-install tests both pass with the canonical SQLite state model.

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
