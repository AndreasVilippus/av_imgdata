# Windows Worker Bundle

The Windows x86_64 bundle is built through MinGW-w64 from the Debian build host.
It includes the worker binaries and requires the native face processor plus the
libvips image processor runtime so HEIC/HEIF and RAW-capable image decoding is
available by default.

Expected build command from repository root:

```powershell
# On Debian build host, not inside PowerShell:
./tools/build-worker.sh --target windows-x86_64
```

Expected bundle layout:

```text
dist/av-imgdata-worker-windows-x86_64/
  bin/
    av-imgdata-worker.exe
  config/
    worker-config.example.json
  jobs/
    sample-worker-job.json
  models/
    README.txt
  work/
  logs/
```

The Windows libvips runtime is built by
`tools/build-native-image-processor-vips-windows.sh` and installed under
`worker/native_deps/windows-x86_64/vips` by default. `VIPS_ROOT` can override
that output/cache location, but it is not a required input dependency. The
build uses a reduced `avimgdata` libvips profile with libde265 HEIC decoding and
without the x265 encoder. It fails if the libvips image processor cannot be
built or bundled, because the worker config enables `image_vips` by default.

If the libvips image processor artifact already exists, use
`AV_IMGDATA_BUILD_WORKER_VIPS=0 ./tools/build-worker.sh --target windows-x86_64`
to rebuild the worker bundle without rebuilding libvips itself.

Local smoke commands on Windows:

```powershell
.\bin\av-imgdata-worker.exe version
.\bin\av-imgdata-worker.exe probe --config .\config\worker-config.example.json
.\bin\av-imgdata-worker.exe once --config .\config\worker-config.example.json --job .\jobs\sample-worker-job.json
```

If the selected configuration file does not exist, `Start-AVImgDataWorker.ps1`
creates it interactively before enrollment/model synchronization. For example:

```powershell
.\Start-AVImgDataWorker.ps1 -ConfigPath .\config\worker-test.json -PathBaseDir \\nas\photo
```

The prompt shows the example configuration values, proposes `worker-01` as the
default worker ID, asks for the Worker API base URL, and leaves worker logging
off by default. Available log levels are `off`, `error`, `warning`, `info`, and
`debug`.

## Windows Security detections

The worker executables are unsigned native MinGW-w64 binaries. Microsoft
Defender can classify rare unsigned binaries as malware or potentially
unwanted software before they have reputation. Do not bypass such a warning
blindly.

Each built bundle contains `SHA256SUMS.txt`. `Start-AVImgDataWorker.ps1`
verifies the worker executables against that manifest before starting them. If
Windows blocks `av-imgdata-worker-api-loop.exe` after the hash check passes,
record the displayed SHA256 value and submit that exact file to Microsoft Security Intelligence
as a suspected false positive. Only allow or exclude the specific
verified file if you trust the build source and the local hash matches the
bundle manifest.
