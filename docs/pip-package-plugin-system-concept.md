# pip Package Plugin System Concept

## Purpose

Optional Python packages should be able to contribute their own status information, activation checks, and runtime capabilities without hard-coding every package into the status page or into `ImgDataService`.

The immediate driver is InsightFace. The same mechanism must also work for future optional packages such as audio metadata libraries.

## Goals

- Keep optional pip package installation explicit and restart-bound.
- Let each optional package define the status data it wants to expose.
- Render package status generically in the UI.
- Keep package-specific runtime checks close to the package integration code.
- Avoid hidden downloads, source builds, or license-sensitive asset downloads.
- Support installation, activation, deactivation, diagnostics, and status extension through one backend registry.

## Non-Goals

- This is not a generic third-party marketplace.
- This does not allow arbitrary user-provided Python code.
- This does not move core package dependencies into optional plugins.
- This does not download model files or other assets automatically.

## Registry Model

The backend should expose a package plugin registry. Each plugin describes one optional pip package group.

Initial plugin fields:

```json
{
  "key": "INSIGHTFACE",
  "label": "InsightFace",
  "enabled_config_path": "pip_packages.INSIGHTFACE.ENABLED",
  "install_on_start_config_path": "pip_packages.INSIGHTFACE.INSTALL_ON_START",
  "requirements_file": "requirements-optional-insightface.txt",
  "wheelhouse_required": true,
  "modules": [
    { "package": "insightface", "module": "insightface.app" },
    { "package": "onnxruntime", "module": "onnxruntime" },
    { "package": "opencv-python-headless", "module": "cv2" }
  ],
  "conflicts": [
    "opencv-python",
    "opencv-contrib-python",
    "opencv-contrib-python-headless"
  ],
  "capabilities": [
    "face_detection",
    "face_recognition"
  ]
}
```

## Backend Contract

Each package plugin should implement a provider object with these functions:

| Function | Purpose |
|---|---|
| `key()` | Stable package key used in config, status, logs, and UI. |
| `default_config()` | Default config fragment merged into `ConfigService.defaultConfig()`. |
| `requirements_file(config)` | Requirements file to install when enabled. |
| `modules(config)` | Import checks and package version checks. |
| `conflicts(config)` | Conflicting installed packages to report. |
| `status(config, install_status)` | Generic and package-specific status payload. |
| `capabilities(config, status)` | Runtime capabilities exposed by the package. |
| `activation_errors(config, status)` | Human-readable blockers before a feature uses the package. |

The registry owns iteration and normalization. Feature code asks the registry for capabilities instead of reading package internals directly.

## Status Payload

The existing `/api/pip_packages_status` endpoint should remain the public entry point. Its `packages` object should be generated from registered package plugins.

Required package status fields:

```json
{
  "label": "InsightFace",
  "enabled": true,
  "install_on_start": true,
  "requirements_file": "requirements-optional-insightface.txt",
  "installed": true,
  "install_status": {
    "status": "success",
    "message": "installed"
  },
  "modules": [
    {
      "package": "insightface",
      "module": "insightface.app",
      "installed": true,
      "version": "0.7.3"
    }
  ],
  "conflicts": [],
  "status_blocks": [
    {
      "key": "models",
      "label_key": "status:pip_models",
      "fallback_label": "Models",
      "value": "buffalo_l (1)"
    }
  ],
  "capabilities": [
    "face_recognition"
  ],
  "activation_errors": []
}
```

`status_blocks` is the generic extension point for the Status page. The UI renders these blocks without knowing package-specific objects like InsightFace models. Existing package-specific fields may stay during migration, but new packages should prefer `status_blocks`.

## UI Contract

The Status page should render:

- package label
- enabled state
- installed state
- last install status
- module summary
- conflicts
- every `status_blocks` entry

The UI must not infer capability from module names. It should display what the backend sends.

The External Libraries area may still provide package-specific configuration controls when required. Status rendering should stay generic.

## Installation And Activation

Installation remains restart-bound:

1. User enables a package.
2. Config is saved.
3. UI shows a restart-required hint.
4. Package start reads enabled plugins.
5. Installer installs only from compatible wheelhouse sources.
6. Installer writes `pip_packages_status.json`.
7. Runtime status merges installer state and live import checks.

Activation is separate from installation. A package is active only if:

- config enables it
- required modules import successfully
- no blocking conflict is present
- package-specific requirements are satisfied

For InsightFace, installed Python modules are not enough. The model status must also be checked before face recognition features run.

## Feature Integration

Feature code should depend on capabilities:

- `face_detection`
- `face_recognition`
- `audio_metadata_tags`
- `audio_rating_mapping`

Example:

```python
if not package_plugins.has_capability("face_recognition"):
    raise RuntimeError("face_recognition_capability_missing")
```

For user-facing flows, missing capability should become a structured status phase or a validation error, not a raw internal exception.

## Proposed Files

Suggested backend structure:

```text
src/services/pip_package_plugins/
  __init__.py
  registry.py
  base.py
  insightface.py
```

Suggested responsibilities:

- `base.py`: provider protocol and shared status helpers
- `registry.py`: registered providers, config merging, status aggregation, capability lookup
- `insightface.py`: InsightFace module checks, conflicts, model status, capabilities

## API Surface

Keep:

- `POST /api/pip_packages_status`

Future-compatible optional endpoints:

- `POST /api/pip_package_plugins_status`
- `POST /api/pip_package_plugins_validate`
- `POST /api/pip_package_plugins_capabilities`

The existing endpoint can already return the new schema, so a new endpoint is not required unless the old response must remain frozen.

## Migration Plan

1. Move the hard-coded `INSIGHTFACE` package spec from `ImgDataService.pipPackagesStatus()` into an InsightFace provider.
2. Add a registry service and let `pipPackagesStatus()` delegate to it.
3. Add `status_blocks` for InsightFace model root, active model, installed model count, and conflicts.
4. Update the Status page to prefer `status_blocks` and keep legacy InsightFace model rendering as fallback.
5. Change InsightFace feature checks to use registry capabilities and activation errors.
6. Add contract tests for generic package rendering and capability validation.

## Failure Behavior

Optional package failures must not block package startup unless a core dependency is involved.

Runtime behavior:

- Installation failure: show status and keep feature disabled.
- Import failure: show module error and keep related capability inactive.
- Missing model or package-specific asset: show activation error.
- Feature start without capability: return structured backend error or operation status phase.

## Security And Licensing

- No source builds on the NAS.
- No automatic model downloads.
- Wheelhouse URLs remain explicit config.
- Package providers must not execute arbitrary user-controlled code.
- License-sensitive assets must be documented and user-managed.

