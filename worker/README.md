# External Worker

This directory contains the future UI-free external worker runtime for AV ImgData.

The worker is intentionally separate from the DSM package runtime:

```text
DSM package
  = controller, DSM authority, job owner, status owner, final write owner

External worker
  = remote execution runtime, DSM Worker API client, local processor runner
```

The worker reuses the same processor contracts and will reuse compatible processor binaries from the same repository, but it is built and packaged as a separate artifact.

## Phase B status

Phase A established the local build and packaging foundation. Phase B adds the first local processor probe.

Implemented through Phase B:

```text
- worker/ project path
- worker-local CMake project
- av-imgdata-worker executable
- version command
- probe command with structured config extraction
- config-relative path resolution
- local face processor path resolution
- local face processor binary existence check
- local face processor version command when binary exists
- local face processor probe command when binary exists
- capability list emitted only when version and probe succeed
- once command with local job-file checks
- run command placeholder
- linux-x86_64 build target
- windows-x86_64 MinGW cross-build target
- docker-linux-x86_64 staging target, currently deferred for validation
- example config
- sample local job
- Linux systemd packaging placeholder
- Windows packaging notes
- Dockerfile and entrypoint
```

Not implemented yet:

```text
- DSM Worker API client
- registration
- heartbeat
- job polling
- file download/upload
- native processor job execution from once mode
- ONNXRuntime/libjpeg/libvips bundle integration
- automatic bundling of av-imgdata-face-processor into worker dist
```

## Commands

```text
av-imgdata-worker version
av-imgdata-worker probe --config <worker-config.json>
av-imgdata-worker once --config <worker-config.json> --job <job.json>
av-imgdata-worker run --config <worker-config.json>
```

## Local build targets

```text
linux-x86_64
windows-x86_64
docker-linux-x86_64
```

Build from repository root:

```bash
bash tools/build-worker.sh --target linux-x86_64
bash tools/build-worker.sh --target windows-x86_64
bash tools/build-worker.sh --target docker-linux-x86_64
```

Optional clean builds:

```bash
bash tools/build-worker.sh --target linux-x86_64 --clean
bash tools/build-worker.sh --target windows-x86_64 --clean
bash tools/build-worker.sh --target docker-linux-x86_64 --clean
```

Docker validation is currently deferred. Optional Docker image build after Docker staging:

```bash
bash tools/build-worker.sh --target docker-linux-x86_64 --docker-build
```

## Debian build host requirements

Baseline:

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential \
  cmake \
  ninja-build \
  git \
  zip \
  unzip
```

For Windows cross-builds:

```bash
sudo apt-get install -y \
  mingw-w64 \
  g++-mingw-w64-x86-64
```

Docker image build requires Docker only when `--docker-build` is used.

## Output layout

Linux:

```text
dist/av-imgdata-worker-linux-x86_64/
  bin/av-imgdata-worker
  config/worker-config.example.json
  jobs/sample-worker-job.json
  models/README.txt
  logs/
  work/
  share/processor_contract/schemas/
```

Windows:

```text
dist/av-imgdata-worker-windows-x86_64/
  bin/av-imgdata-worker.exe
  config/worker-config.example.json
  jobs/sample-worker-job.json
  models/README.txt
  logs/
  work/
  share/processor_contract/schemas/
```

Docker staging:

```text
dist/av-imgdata-worker-docker-linux-x86_64/
  Dockerfile
  entrypoint.sh
  bin/av-imgdata-worker
  config/worker-config.example.json
  jobs/sample-worker-job.json
  models/README.txt
  share/processor_contract/schemas/
```

## Smoke tests

Linux:

```bash
dist/av-imgdata-worker-linux-x86_64/bin/av-imgdata-worker version
dist/av-imgdata-worker-linux-x86_64/bin/av-imgdata-worker probe \
  --config dist/av-imgdata-worker-linux-x86_64/config/worker-config.example.json
dist/av-imgdata-worker-linux-x86_64/bin/av-imgdata-worker once \
  --config dist/av-imgdata-worker-linux-x86_64/config/worker-config.example.json \
  --job dist/av-imgdata-worker-linux-x86_64/jobs/sample-worker-job.json
```

Windows, after copying the bundle to Windows 11:

```powershell
.\bin\av-imgdata-worker.exe version
.\bin\av-imgdata-worker.exe probe --config .\config\worker-config.example.json
.\bin\av-imgdata-worker.exe once --config .\config\worker-config.example.json --job .\jobs\sample-worker-job.json
```

Docker:

```bash
docker build -t av-imgdata-worker:phase-b dist/av-imgdata-worker-docker-linux-x86_64
docker run --rm av-imgdata-worker:phase-b version
```

## Phase B probe behavior

`probe` reads `worker-config.example.json`, extracts the configured face processor, resolves relative paths against the config file directory, and attempts:

```text
<face_processor> version
<face_processor> probe --model-root <model_root> --model-name <model_name>
```

If the face processor binary is not present in the worker bundle yet, `probe` still returns a valid worker JSON payload with:

```json
{
  "face_processor_binary_exists": false,
  "capabilities": []
}
```

Capabilities are advertised only when both `version` and `probe` succeed.

## Directory policy

Worker-specific build files belong below this directory. This includes worker-only CMake toolchains.

Shared processor code belongs below `processors/native/`.

DSM package build logic remains below `SynoBuildConf/` and package build scripts in `tools/`.
