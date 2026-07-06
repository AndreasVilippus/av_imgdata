# Worker CMake Toolchains

This directory is for toolchain files that are specific to external worker bundle builds.

Keep worker-only toolchains here instead of a top-level `cmake/` directory while they are not shared by the DSM package build.

Planned files:

```text
linux-x86_64.cmake
windows-mingw-x86_64.cmake
```

A top-level `cmake/` directory should only be introduced if CMake modules or toolchains are shared by multiple repository build families, for example both external worker builds and non-Synology native processor builds.
