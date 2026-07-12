# External Worker Platform Contract

AV ImgData distributes two external worker platform artifacts through the DSM package:

```text
av-imgdata-worker-windows-x86_64.zip
av-imgdata-worker-linux-x86_64.tar.gz
```

The Unix artifact is the Linux/Unix runtime. Docker staging may reuse the Unix binaries, but it is not a third independent worker protocol implementation.

## Shared runtime roles

Both platform artifacts contain the same functional roles:

```text
av-imgdata-worker
  Executes one local processor-contract job and provides readiness probes.

av-imgdata-worker-api-loop
  Registers the worker, sends heartbeats, claims jobs, and returns results.

av-imgdata-worker-configure
  Writes the canonical versioned worker configuration.

av-imgdata-worker-model-sync
  Downloads DSM-authorized model files and verifies their SHA-256 hashes.
```

Windows uses the `.exe` variants. Unix uses executable files without a suffix.

Both artifacts also contain:

```text
config/worker-config.example.json
config/worker-config.schema.json
share/worker_protocol/worker-protocol.json
```

## Single-source rules

The following files are authoritative:

```text
worker/protocol/worker-protocol.json
worker/config/worker-config.schema.json
worker/include/av_imgdata/worker_runtime.h
```

Generated protocol constants are consumed by Python and C++. Platform installers must not redefine capabilities, versions, configuration defaults, model manifest processing, or hash verification.

## Platform-specific responsibilities

Windows PowerShell owns only:

```text
- enrollment HTTP call
- Windows token ACL
- invoking the shared configure and model-sync binaries
```

The Unix shell initializer owns only:

```text
- enrollment HTTP call
- Unix token mode 0600
- invoking the shared configure and model-sync binaries
```

## Status ownership

DSM remains the status and persistence authority. External worker status payloads use:

```text
schema_version
component = external_worker
phase
protocol_version
```

The UI must render backend-provided worker status and must not infer registration, readiness, or job state from platform-specific files.

## Required tests

Repository tests must cover:

```text
- generated protocol files are current
- Python and C++ constants match the descriptor
- Unix CMake build and CTest execution
- Windows MinGW cross-build when the toolchain is available
- identical runtime roles in both installed artifacts
- canonical config generation
- path traversal rejection
- explicit register-before-heartbeat lifecycle
- thin Windows and Unix initializers
- one DSM Worker API composition root and one HTTP error mapping
```
