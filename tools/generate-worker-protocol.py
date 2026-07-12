#!/usr/bin/env python3
"""Generate Python and C++ worker protocol constants from one descriptor."""

import argparse
import json
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "worker" / "protocol" / "worker-protocol.json"
DEFAULT_PYTHON = PROJECT_ROOT / "src" / "services" / "worker_protocol_generated.py"
DEFAULT_CPP = PROJECT_ROOT / "worker" / "include" / "av_imgdata" / "worker_protocol.h"


def _tuple_lines(values: Iterable[str], indent: str = "    ") -> str:
    return "\n".join(f'{indent}"{value}",' for value in values)


def render_python(data: dict) -> str:
    return f'''#!/usr/bin/env python3
"""Generated from worker/protocol/worker-protocol.json. Do not edit manually."""

PROTOCOL_VERSION = "{data["protocol_version"]}"
WORKER_VERSION = "{data["worker_version"]}"
CONFIG_SCHEMA_VERSION = {int(data["config_schema_version"])}
STATE_SCHEMA_VERSION = {int(data["state_schema_version"])}
TOKEN_SCOPES = (
{_tuple_lines(data["token_scopes"])}
)
CAPABILITIES = (
{_tuple_lines(data["capabilities"])}
)
INPUT_MODES = (
{_tuple_lines(data["input_modes"])}
)
'''


def render_cpp(data: dict) -> str:
    capabilities = _tuple_lines(data["capabilities"], "    ")
    input_modes = _tuple_lines(data["input_modes"], "    ")
    scopes = _tuple_lines(data["token_scopes"], "    ")
    return f'''#pragma once

// Generated from worker/protocol/worker-protocol.json. Do not edit manually.
#include <array>
#include <cstddef>
#include <string>

namespace av_imgdata::worker {{

inline constexpr const char* kProtocolVersion = "{data["protocol_version"]}";
inline constexpr const char* kWorkerVersion = "{data["worker_version"]}";
inline constexpr int kConfigSchemaVersion = {int(data["config_schema_version"])};
inline constexpr int kStateSchemaVersion = {int(data["state_schema_version"])};

inline constexpr std::array<const char*, {len(data["token_scopes"])}> kTokenScopes = {{
{scopes}
}};
inline constexpr std::array<const char*, {len(data["capabilities"])}> kCapabilities = {{
{capabilities}
}};
inline constexpr std::array<const char*, {len(data["input_modes"])}> kInputModes = {{
{input_modes}
}};

template <std::size_t N>
inline std::string json_string_array(const std::array<const char*, N>& values) {{
    std::string result = "[";
    bool first = true;
    for (const char* value : values) {{
        if (!first) result += ',';
        first = false;
        result += '\"';
        result += value;
        result += '\"';
    }}
    result += ']';
    return result;
}}

inline std::string capabilities_json() {{ return json_string_array(kCapabilities); }}
inline std::string input_modes_json() {{ return json_string_array(kInputModes); }}

namespace config_key {{
inline constexpr const char* kSchemaVersion = "schema_version";
inline constexpr const char* kWorkerId = "worker_id";
inline constexpr const char* kWorkerApiBaseUrl = "worker_api_base_url";
inline constexpr const char* kWorkspaceRoot = "workspace_root";
inline constexpr const char* kPathBaseDir = "path_base_dir";
inline constexpr const char* kPollIntervalSeconds = "poll_interval_seconds";
inline constexpr const char* kAuth = "auth";
inline constexpr const char* kTokenFile = "token_file";
inline constexpr const char* kProcessors = "processors";
inline constexpr const char* kFace = "face";
inline constexpr const char* kModelRoot = "model_root";
inline constexpr const char* kModelName = "model_name";
}}  // namespace config_key

}}  // namespace av_imgdata::worker
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--python-output", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--cpp-output", type=Path, default=DEFAULT_CPP)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.source.read_text(encoding="utf-8"))
    outputs = {
        args.python_output: render_python(data),
        args.cpp_output: render_cpp(data),
    }
    stale = []
    for path, expected in outputs.items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(str(path))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")
    if stale:
        raise SystemExit("stale generated worker protocol files: " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
