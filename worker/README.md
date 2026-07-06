# External Worker

This directory contains the future UI-free external worker runtime for AV ImgData.

The worker is intentionally separate from the DSM package runtime:

```text
DSM package
  = controller, DSM authority, job owner, status owner, final write owner

External worker
  = remote execution runtime, DSM Worker API client, local processor runner
```

The worker should reuse the same processor contracts and processor binaries as the DSM package, but it is built and packaged as a separate artifact.

## Planned commands

```text
av-imgdata-worker version
av-imgdata-worker probe --config <worker-config.json>
av-imgdata-worker once --config <worker-config.json> --job <job.json>
av-imgdata-worker run --config <worker-config.json>
```

## Planned first targets

```text
linux-x86_64
windows-x86_64
docker-linux-x86_64
```

## Directory policy

Worker-specific build files belong below this directory. This includes worker-only CMake toolchains.

Shared processor code belongs below `processors/native/`.

DSM package build logic remains below `SynoBuildConf/` and package build scripts in `tools/`.
