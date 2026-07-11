# Qt 6 Worker GUI under LGPLv3

## Status

Proposed architecture and licensing concept for introducing a native Qt 6 GUI for the external AV ImgData workers.

This document is a technical compliance concept, not legal advice. The exact Qt release, module list and shipped binaries must be reviewed for every release artifact.

## Decision

The external Windows and Linux worker GUIs may use Qt 6 under the GNU Lesser General Public License version 3 (LGPLv3), provided that:

- the GUI is implemented in C++ without Python bindings;
- Qt is used as shared libraries and linked dynamically;
- Qt DLLs/shared objects remain separate and replaceable;
- no Qt module that is GPL-only for open-source users is linked into the proprietary/MIT worker GUI;
- the complete corresponding source code for the shipped LGPL Qt libraries, including local modifications, is supplied or made available through a valid written offer;
- LGPLv3, Qt copyright notices and all applicable third-party notices are shipped prominently;
- the user is not contractually or technically prevented from debugging, replacing or relinking the LGPL libraries;
- the exact deployed Qt files and third-party components are recorded in a release manifest/SBOM.

Recommended baseline:

```text
C++17 or newer
CMake
Qt 6 shared build
Qt Widgets for the first GUI
Qt Core + GUI + Widgets + Network + Concurrent
Windows deployment with windeployqt
Linux deployment with explicit shared-library packaging rules
```

Qt Quick/QML is possible, but Qt Widgets is preferred for the first worker GUI because it has a smaller deployment surface, fewer runtime plugins and fewer opportunities to accidentally include GPL-only add-ons.

## Project licensing compatibility

The repository root is licensed under the MIT License. MIT permits use, modification, distribution and sublicensing, subject to retaining its copyright and permission notice.

The MIT license does not exclude or conflict with dynamically linking the worker application against LGPLv3 Qt libraries. The worker executable can remain under MIT or another chosen application license while Qt remains under LGPLv3.

The licenses must not be merged into one statement. Distribution must clearly distinguish:

```text
AV ImgData worker application code -> MIT
Qt libraries and plugins            -> LGPLv3, unless a module states otherwise
Qt build tools                       -> GPLv3 with Qt GPL Exception or commercial terms
Qt third-party code                  -> component-specific licenses
Other worker dependencies            -> their individual licenses
```

The LGPL obligations apply to the Qt library portion and the manner in which the combined application is distributed. They do not automatically require publication of the MIT application source when Qt is dynamically linked and all LGPLv3 requirements are met.

## Architecture

```text
av-imgdata-worker-gui.exe
├── proprietary/MIT worker application code
├── existing worker API client and process control
├── Qt6Core.dll
├── Qt6Gui.dll
├── Qt6Widgets.dll
├── Qt6Network.dll
├── optional Qt6Concurrent.dll
├── platforms/qwindows.dll
├── styles/ and imageformats/ plugins actually required
├── licenses/
│   ├── AV_IMGDATA-MIT.txt
│   ├── LGPL-3.0.txt
│   ├── QT-NOTICE.txt
│   └── THIRD-PARTY-NOTICES.txt
├── sources/
│   └── qt-source-offer.txt or corresponding Qt source archive
└── manifests/
    ├── qt-deployment-manifest.json
    └── sbom.spdx.json
```

The GUI should control the existing worker runtime instead of duplicating its business logic. Preferred integration:

```text
Qt GUI
  -> worker configuration editor
  -> worker service/process start and stop
  -> Worker API connection status
  -> job/progress/log display
  -> diagnostics and dependency checks
  -> existing worker executable and processor binaries
```

The first implementation should either:

1. link reusable worker runtime code into a non-Qt internal application library, or
2. run `av-imgdata-worker-api-loop` as a child process through `QProcess` and consume structured output.

Option 2 gives the strongest separation and the lowest initial regression risk.

## Dynamic linking requirements

### Windows

Qt must be deployed as separate DLLs. Do not statically link Qt into the worker executable.

Expected deployment files include only those actually required:

```text
Qt6Core.dll
Qt6Gui.dll
Qt6Widgets.dll
Qt6Network.dll
Qt6Concurrent.dll             optional
platforms/qwindows.dll
imageformats/qjpeg.dll        when needed
imageformats/qpng.dll         when needed
styles/qmodernwindowsstyle.dll when selected and available
```

`windeployqt` may generate the initial deployment directory, but its result must be audited. It can copy plugins and libraries that are not required by the application.

Example:

```powershell
windeployqt.exe `
  --release `
  --no-translations `
  --no-opengl-sw `
  .\bin\av-imgdata-worker-gui.exe
```

The final packaging script must generate a file-level manifest with names, versions, hashes, source package references and licenses.

The worker installer must not:

- merge Qt DLLs into the executable;
- encrypt or rename Qt libraries to prevent replacement;
- reject all user-replaced compatible Qt DLLs solely because they are not vendor-signed;
- impose an EULA prohibition on reverse engineering where LGPLv3 permits it for debugging modifications to Qt;
- use an application-store delivery mechanism whose terms remove LGPL rights.

Normal operating-system security controls remain possible, but the shipped product must provide sufficient installation information to run a legitimately relinked/replaced Qt library.

### Linux

Qt must be dynamically linked against `.so` files. Packaging may use system Qt packages or application-local Qt libraries.

Application-local deployment is recommended for reproducibility, provided the shared objects remain separate and replaceable.

Runtime lookup should use a controlled relative path such as `$ORIGIN/../lib`, without embedding Qt into the executable.

Example:

```cmake
set_target_properties(av-imgdata-worker-gui PROPERTIES
    INSTALL_RPATH "$ORIGIN/../lib"
)
```

Do not assume that copying Linux Qt libraries alone is sufficient. Platform plugins, XCB/Wayland dependencies, font/rendering libraries and their notices must be included in the deployment review.

## Recommended CMake integration

```cmake
cmake_minimum_required(VERSION 3.21)
project(av_imgdata_worker_gui LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Qt6 REQUIRED COMPONENTS
    Core
    Gui
    Widgets
    Network
    Concurrent
)

qt_standard_project_setup()

qt_add_executable(av-imgdata-worker-gui
    gui/main.cpp
    gui/main_window.cpp
    gui/main_window.h
)

target_link_libraries(av-imgdata-worker-gui PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    Qt6::Network
    Qt6::Concurrent
)

install(TARGETS av-imgdata-worker-gui RUNTIME DESTINATION bin)
```

The Qt installation used by `find_package` must be a shared build. CI must reject a static Qt package.

Suggested CI check:

```text
- inspect linked libraries after build
- fail when Qt is statically embedded
- fail when a GPL-only Qt module is found
- fail when an undeclared Qt plugin is staged
- verify license and source-offer files exist
- generate SBOM and hashes
```

## Module policy

Qt changes module licensing over time. The module decision must therefore be tied to the exact Qt version in the release manifest. The following matrix is the project policy for the currently documented Qt 6 line.

### Approved core modules

| Module | Typical purpose in worker GUI | Policy | Notes |
|---|---|---:|---|
| Qt Core | Event loop, files, settings, JSON, processes, threads | Approved | Required base module. |
| Qt GUI | Fonts, images, clipboard, window-system integration | Approved | Required by Widgets. |
| Qt Widgets | Native desktop controls and dialogs | Approved | Preferred first GUI technology. |
| Qt Network | HTTPS Worker API, proxy/TLS support | Approved | Audit TLS backend and shipped plugins. |
| Qt Concurrent | Background tasks and futures | Approved | Optional; avoid blocking the GUI thread. |
| Qt Test | Automated tests | Approved for development | Normally not shipped in production. |
| Qt SQL | Local structured state through SQL drivers | Approved with review | Each shipped database driver and client library needs separate review. Prefer not to add a database for GUI-only state. |
| Qt XML | XML parsing | Approved if needed | No current requirement. |
| Qt OpenGL / OpenGLWidgets | Accelerated custom rendering | Approved with review | Not needed for the initial GUI. Adds driver and graphics complexity. |
| Qt Print Support | Printing/export dialogs | Approved if needed | No worker requirement expected. |
| Qt DBus | Linux desktop/service integration | Approved on Linux with review | Platform-specific; not needed on Windows. |
| Qt Linguist runtime support | Translations | Approved | Build tools are not runtime libraries; see tools section. |

### Conditionally usable add-on modules

These may be used only after a release-specific license and deployment review:

| Module | Policy reason |
|---|---|
| Qt QML / Qt Quick | Generally usable where offered under LGPLv3, but expands runtime, plugin and QML deployment surface. Do not combine with GPL-only QML compiler/add-ons. |
| Qt Quick Controls | Verify exact module licensing and deployed style plugins for the selected Qt version. |
| Qt SVG | Useful for icons; review shipped third-party notices and parsers. |
| Qt Multimedia | Large backend and codec dependency surface; codec patent and platform licensing must be reviewed. |
| Qt WebSockets | May be used if Worker API adopts WebSockets; not required initially. |
| Qt WebChannel | Only with a justified embedded/web integration. |
| Qt WebEngine | Technically possible where available under acceptable terms, but strongly discouraged because Chromium introduces a very large third-party notice, source and security-update burden. |
| Qt Positioning / Sensors / Serial Port / Serial Bus / Bluetooth / NFC | No current worker requirement; platform and third-party dependencies require review. |
| Qt 3D | No current requirement; large deployment surface. |
| Qt Shader Tools | Mostly build-time; generated artifacts and tool licensing must be separated from runtime licensing. |
| Qt Image Formats | Ship only required plugins and their notices. Avoid copying all plugins by default. |

### Prohibited under the LGPL worker policy

According to the current Qt licensing documentation, the following modules are available to open-source users under GPLv3 rather than LGPLv3. They must not be linked or shipped with a closed/MIT worker GUI unless the complete application is intentionally distributed under GPLv3 or a commercial Qt license is purchased:

- Qt Canvas Painter
- Qt CoAP
- Qt Graphs
- Qt GRPC
- Qt HTTP Server
- Qt Lottie Animation
- Qt MQTT
- Qt Network Authorization
- Qt Qml Compiler
- Qt Quick 3D
- Qt Quick 3D Physics
- Qt Quick Timeline
- Qt Virtual Keyboard
- Qt Wayland Compositor

This list must be regenerated from the documentation of the exact pinned Qt version. It is not safe to copy the list permanently without version verification.

A module name appearing in the Qt installer does not mean that it is available under LGPLv3.

## Qt tools and utilities

Qt build and development tools are generally offered under GPLv3 with the Qt GPL Exception or under commercial terms. Examples include:

```text
moc
uic
rcc
qmake
windeployqt
Qt Creator
Linguist tools
QML build tools
```

Using a GPL-covered tool to build the application does not by itself make the generated application GPL, especially where the Qt GPL Exception applies. However:

- these tools should remain build dependencies and should not be shipped as worker runtime components unless needed;
- tool license texts must be retained in the build environment/distribution when the tool itself is redistributed;
- generated code must be checked for its own notices;
- GPL-only runtime libraries must not be mistaken for harmless build tools.

## Third-party code inside Qt

Qt contains third-party components under MIT, BSD, Apache-2.0, zlib, Unicode, FreeType and other licenses. Some components present GPL as one alternative among multiple licenses. The selected, distributable license option and required notices must be recorded.

Only components actually shipped need to be included in the product notice set, but `windeployqt` and Linux deployment tools can change that set. Therefore the notice file must be generated from the final staged artifact, not from the CMake module list alone.

Starting with Qt 6.8, Qt publishes SPDX SBOM data for third-party components. The packaging pipeline should consume that data and filter it to the shipped files/modules.

Important distinction:

```text
GPL mentioned as one optional license for embedded third-party code
    != automatically a GPL-only Qt module

Qt module explicitly listed as GPL-only for open-source users
    = prohibited for the closed/MIT LGPL worker policy
```

For example, a library may be available under a permissive license or GPL as alternatives. The permissive alternative can be used when its conditions are met.

## Interaction with existing package dependencies

The repository currently uses or prepares worker bundles with components including ONNX Runtime, libjpeg/libjpeg-turbo, curl-based HTTP transport and optionally libvips. These do not inherently exclude Qt 6, but their licenses and linkage must remain independently compliant.

| Existing component/category | Qt compatibility assessment | Required action |
|---|---|---|
| AV ImgData MIT application code | Compatible | Keep MIT notice in source and binary distributions. |
| ONNX Runtime | No inherent conflict with LGPL Qt dynamic linking | Pin version; include its license and third-party notices. Review optional execution providers separately. |
| libjpeg/libjpeg-turbo | No inherent conflict | Include applicable BSD/IJG/zlib notices for shipped binaries. |
| curl/libcurl or curl executable | No inherent conflict | Include curl license and TLS/backend notices. Do not duplicate network stacks without reason; Qt Network may replace GUI-side shelling out to curl. |
| libvips | No inherent conflict when obligations are fulfilled | Treat libvips as a separate LGPL component, dynamically link where applicable, provide source/offer and notices for it and its dependency chain. |
| C/C++ runtime libraries | Depends on toolchain/runtime | Record MinGW/MSVC/GCC runtime terms. Static linking of libgcc/libstdc++ does not make Qt static, but runtime license exceptions and source obligations must still be reviewed. |
| Face-analysis models | Independent of Qt | Model/data licenses may restrict commercial or redistribution use even when the code licenses are compatible. Keep model review as a release gate. |
| DSM package scripts and Python backend | Independent of GUI linkage | Qt is for external worker artifacts only unless a separate DSM architecture decision is made. |

No license currently identified in the repository root excludes introducing Qt 6 under LGPLv3. The main exclusion is the reverse direction: GPL-only Qt modules would impose requirements incompatible with retaining the worker GUI solely under MIT/closed distribution.

A complete conclusion requires a generated inventory of every binary placed into the worker ZIP/TAR artifact. Source-code repository licensing alone is insufficient.

## Special risks

### GPL-only Qt modules

This is the primary module-selection risk. Dynamic linking does not avoid GPL obligations when the linked Qt module itself is GPL-only.

### Static Qt builds

Static Qt is prohibited by project policy. LGPLv3 static-link compliance can require relinkable application object files and installation information, and creates uncertainty about whether the application remains merely a work using the library.

The existing MinGW options `-static-libgcc` and `-static-libstdc++` affect compiler runtime libraries, not Qt. They do not permit static Qt. The build must still show imports from separate Qt DLLs.

### Closed or signed appliances

LGPLv3 requires that recipients can run a modified/relinked version of the LGPL library. If future worker deployment uses a locked appliance, mandatory signature chain or immutable container policy that blocks modified Qt libraries, commercial Qt licensing should be evaluated.

### Qt WebEngine

WebEngine should not be used for a worker status interface that can be implemented with Widgets. Chromium significantly increases binary size, third-party attribution, source-availability and security-maintenance obligations.

### Plugins copied implicitly

Qt platform, image, TLS, SQL and style plugins are libraries and must be included in module/license analysis. Runtime plugin discovery can also accidentally load unreviewed system plugins. The application should use a controlled plugin path.

### Models and media codecs

Qt compatibility does not cure a non-commercial model license or a codec/patent restriction. Models and codecs remain separate release gates.

## Required release artifacts

Every worker GUI release must contain or reference:

```text
licenses/AV_IMGDATA-MIT.txt
licenses/LGPL-3.0.txt
licenses/QT-NOTICE.txt
licenses/THIRD-PARTY-NOTICES.txt
sources/qt-source-offer.txt
manifests/qt-deployment-manifest.json
manifests/sbom.spdx.json
```

`qt-deployment-manifest.json` should contain at least:

```json
{
  "qt_version": "exact version",
  "qt_source_package": "exact source archive or commit",
  "build_type": "shared",
  "toolchain": "exact compiler and runtime",
  "modules": [],
  "plugins": [],
  "files": [
    {
      "path": "bin/Qt6Core.dll",
      "sha256": "...",
      "license": "LGPL-3.0-only OR GPL-3.0-only OR LicenseRef-Qt-Commercial"
    }
  ],
  "local_qt_modifications": []
}
```

For the LGPL distribution path, the release process must choose and implement one valid source-delivery method:

1. include the complete corresponding Qt source with the release;
2. host the exact corresponding source for the legally required period and provide durable instructions; or
3. include a legally reviewed written offer with durable fulfillment procedures.

A generic link to the current Qt download page is not sufficient as the only long-term source fulfillment process because versions can disappear or change.

## User-facing notice

The worker GUI should include an `About > Open Source Licenses` page stating at least:

```text
This product uses Qt under the GNU Lesser General Public License version 3.
Qt is Copyright The Qt Company Ltd. and other contributors.
You may replace the Qt shared libraries with compatible modified versions in
accordance with LGPLv3. License texts, source availability information and
third-party notices are included with this installation.
```

The notice must not imply that The Qt Company endorses AV ImgData.

## Packaging and CI implementation plan

### Phase 1: technical prototype

- Add an optional `AV_IMGDATA_WORKER_BUILD_QT_GUI` CMake option, default `OFF`.
- Require an explicit shared Qt installation.
- Implement a minimal Qt Widgets window.
- Start the existing API-loop executable using `QProcess`.
- Display structured status and logs.
- Do not add optional Qt modules during the prototype.

### Phase 2: audited deployment

- Add Windows `windeployqt` staging.
- Add Linux library/plugin staging.
- Create a fixed allowlist for Qt modules and plugins.
- Generate hashes and an SPDX SBOM.
- Produce third-party notices from the final staged tree.
- Archive the exact Qt source package and SBOM data.

### Phase 3: compliance tests

Static tests should fail the build when:

```text
- Qt is not dynamically linked
- a GPL-only Qt module is linked or copied
- unexpected Qt DLLs/plugins are present
- LGPL and notice files are missing
- the Qt source package/offer is missing
- the manifest does not match the artifact
- a Qt library is embedded into the application executable
```

Windows verification examples:

```powershell
dumpbin /DEPENDENTS .\bin\av-imgdata-worker-gui.exe
objdump -p .\bin\av-imgdata-worker-gui.exe
```

Expected result: imports reference separate `Qt6*.dll` files.

Linux verification examples:

```bash
ldd bin/av-imgdata-worker-gui
readelf -d bin/av-imgdata-worker-gui
```

Expected result: `NEEDED` entries reference separate Qt shared objects.

## Approval checklist

Before enabling the Qt GUI in a public worker bundle:

- [ ] Exact Qt version is pinned.
- [ ] Qt came from an open-source shared build, not a commercial-only package.
- [ ] Only approved LGPL-eligible modules are linked.
- [ ] No GPL-only module or runtime plugin is staged.
- [ ] Qt DLLs/shared objects are separate and replaceable.
- [ ] Application terms do not prohibit LGPL-permitted reverse engineering.
- [ ] LGPLv3 and prominent Qt notice are included.
- [ ] Exact corresponding Qt source is archived or covered by a valid source offer.
- [ ] Modifications to Qt, if any, are documented and made available.
- [ ] Third-party notices are generated from the shipped files.
- [ ] Existing worker dependencies are represented in the SBOM.
- [ ] Model and codec licenses have independent approval.
- [ ] Windows and Linux linkage tests pass.
- [ ] Final artifact receives legal review before first external/customer distribution.

## Recommendation

Proceed with a Qt 6 Widgets prototype using only:

```text
Qt Core
Qt GUI
Qt Widgets
Qt Network
Qt Concurrent (only when needed)
```

Use dynamic linking exclusively, keep Qt libraries and plugins separate, and make the artifact-level license/SBOM check part of the worker build.

Do not introduce any GPL-only Qt module. If a future requirement needs one of those modules, either replace it with an LGPL/permissive alternative, license the complete application under GPLv3, or purchase an appropriate commercial Qt license.

## Authoritative references

- Qt Licensing: https://doc.qt.io/qt-6/licensing.html
- Qt open-source obligations: https://www.qt.io/development/open-source-lgpl-obligations
- Third-party code used in Qt: https://doc.qt.io/qt-6/licenses-used-in-qt.html
- Qt module index: https://doc.qt.io/qt-6/qtmodules.html
- GNU LGPLv3: https://www.gnu.org/licenses/lgpl-3.0.html

The URLs above point to current documentation. The release process must archive or record the version-specific pages and source/SBOM material used for the actual Qt release.