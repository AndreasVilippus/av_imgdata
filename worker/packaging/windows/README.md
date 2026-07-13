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
