#pragma once

#include <array>
#include <string>

namespace av_imgdata::worker {

inline constexpr const char* kProtocolVersion = "1.0";
inline constexpr const char* kWorkerVersion = "0.10.0";

inline constexpr std::array<const char*, 7> kCapabilities = {
    "face_native_detect",
    "face_native_embed",
    "face_native_detect_batch",
    "face_native_embed_batch",
    "face_native_rank_embeddings",
    "face_native_profile_math",
    "warm_processor_worker",
};

inline constexpr std::array<const char*, 1> kInputModes = {
    "shared_path",
};

inline std::string json_string_array(const auto& values) {
    std::string result = "[";
    bool first = true;
    for (const char* value : values) {
        if (!first) result += ',';
        first = false;
        result += '"';
        result += value;
        result += '"';
    }
    result += ']';
    return result;
}

inline std::string capabilities_json() {
    return json_string_array(kCapabilities);
}

inline std::string input_modes_json() {
    return json_string_array(kInputModes);
}

namespace config_key {
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
}  // namespace config_key

}  // namespace av_imgdata::worker
