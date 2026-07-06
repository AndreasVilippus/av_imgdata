# Windows Worker Bundle

Phase A creates a local Windows x86_64 bundle through MinGW-w64 from the Debian build host.

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

Phase A does not bundle ONNXRuntime, libjpeg, libvips, or the face processor yet. Those are Phase B/C processor execution requirements.

Local smoke commands on Windows:

```powershell
.\bin\av-imgdata-worker.exe version
.\bin\av-imgdata-worker.exe probe --config .\config\worker-config.example.json
.\bin\av-imgdata-worker.exe once --config .\config\worker-config.example.json --job .\jobs\sample-worker-job.json
```
