#include <array>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#define POPEN _popen
#define PCLOSE _pclose
#else
#define POPEN popen
#define PCLOSE pclose
#endif

#ifndef AV_IMGDATA_WORKER_VERSION
#define AV_IMGDATA_WORKER_VERSION "0.1.0-phase-d"
#endif

namespace {

struct WorkerConfig {
    std::string config_path;
    std::string config_dir;
    std::string worker_id;
    std::string dsm_base_url;
    std::string workspace_root;
    std::string face_path;
    std::string face_model_root;
    std::string face_model_name;
    int poll_interval_seconds = 2;
};

struct FaceModelStatus {
    std::string model_dir;
    std::string detector_path;
    std::string recognizer_path;
    std::string manifest_path;
    std::string license_ack_path;
    bool detector_present = false;
    bool recognizer_present = false;
    bool manifest_present = false;
    bool license_ack_present = false;
};

struct CommandResult {
    int exit_code = -1;
    std::string output;
};

std::string arg_value(const std::vector<std::string>& args, const std::string& name) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i) {
        if (args[i] == name) {
            return args[i + 1];
        }
    }
    return "";
}

bool has_arg(const std::vector<std::string>& args, const std::string& name) {
    for (const std::string& item : args) {
        if (item == name) {
            return true;
        }
    }
    return false;
}

int parse_int(const std::string& value, int fallback) {
    if (value.empty()) {
        return fallback;
    }
    char* end = NULL;
    const long parsed = std::strtol(value.c_str(), &end, 10);
    if (end == value.c_str()) {
        return fallback;
    }
    return static_cast<int>(parsed);
}

bool is_path_separator(char c) {
    return c == '/' || c == '\\';
}

std::string dirname_of(const std::string& path) {
    const std::size_t pos = path.find_last_of("/\\");
    if (pos == std::string::npos) {
        return ".";
    }
    if (pos == 0) {
        return path.substr(0, 1);
    }
    return path.substr(0, pos);
}

std::string basename_of(const std::string& path) {
    const std::size_t pos = path.find_last_of("/\\");
    if (pos == std::string::npos) {
        return path;
    }
    return path.substr(pos + 1);
}

bool looks_absolute(const std::string& path) {
    if (path.empty()) {
        return false;
    }
    if (path.size() >= 2 && path[1] == ':') {
        return true;
    }
    if (path.size() >= 2 && is_path_separator(path[0]) && is_path_separator(path[1])) {
        return true;
    }
    return is_path_separator(path[0]);
}

std::string join_path(const std::string& base, const std::string& path) {
    if (path.empty() || looks_absolute(path)) {
        return path;
    }
    if (base.empty() || base == ".") {
        return path;
    }
    const char sep = base.find('\\') != std::string::npos ? '\\' : '/';
    if (is_path_separator(base.back())) {
        return base + path;
    }
    return base + sep + path;
}

bool file_exists(const std::string& path) {
    if (path.empty()) {
        return false;
    }
    std::ifstream input(path.c_str(), std::ios::binary);
    return static_cast<bool>(input);
}

std::string read_file(const std::string& path) {
    std::ifstream input(path.c_str(), std::ios::binary);
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

bool write_file(const std::string& path, const std::string& text) {
    std::ofstream output(path.c_str(), std::ios::binary);
    if (!output) {
        return false;
    }
    output << text;
    return static_cast<bool>(output);
}

std::string trim_output(std::string value) {
    while (!value.empty() && (value.back() == '\n' || value.back() == '\r' || value.back() == ' ' || value.back() == '\t')) {
        value.pop_back();
    }
    return value;
}

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (char c : value) {
        switch (c) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << c; break;
        }
    }
    return out.str();
}

std::string shell_quote(const std::string& value) {
#ifdef _WIN32
    std::string out = "\"";
    for (char c : value) {
        if (c == '"') {
            out += "\\\"";
        } else {
            out += c;
        }
    }
    out += "\"";
    return out;
#else
    std::string out = "'";
    for (char c : value) {
        if (c == '\'') {
            out += "'\\''";
        } else {
            out += c;
        }
    }
    out += "'";
    return out;
#endif
}

std::string build_processor_command(const std::string& executable, const std::vector<std::string>& arguments) {
#ifdef _WIN32
    std::string command = "cmd.exe /S /C \"\"";
    command += executable;
    command += "\"";
    for (const std::string& argument : arguments) {
        command += " \"";
        for (char c : argument) {
            if (c == '"') {
                command += "\\\"";
            } else {
                command += c;
            }
        }
        command += "\"";
    }
    command += " 2>&1\"";
    return command;
#else
    std::string command = shell_quote(executable);
    for (const std::string& argument : arguments) {
        command += " ";
        command += shell_quote(argument);
    }
    command += " 2>&1";
    return command;
#endif
}

CommandResult run_command_capture(const std::string& command) {
    CommandResult result;
    std::array<char, 256> buffer{};
    FILE* pipe = POPEN(command.c_str(), "r");
    if (!pipe) {
        result.exit_code = -1;
        result.output = "popen_failed";
        return result;
    }
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        result.output += buffer.data();
    }
    result.exit_code = PCLOSE(pipe);
    result.output = trim_output(result.output);
    return result;
}

CommandResult run_processor_capture(const std::string& executable, const std::vector<std::string>& arguments) {
    return run_command_capture(build_processor_command(executable, arguments));
}

std::string extract_json_string(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    std::size_t pos = json.find(needle);
    if (pos == std::string::npos) {
        return "";
    }
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) {
        return "";
    }
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) {
        return "";
    }
    ++pos;
    std::string value;
    bool escaping = false;
    for (; pos < json.size(); ++pos) {
        const char c = json[pos];
        if (escaping) {
            switch (c) {
                case 'n': value += '\n'; break;
                case 'r': value += '\r'; break;
                case 't': value += '\t'; break;
                case '\\': value += '\\'; break;
                case '"': value += '"'; break;
                default: value += c; break;
            }
            escaping = false;
        } else if (c == '\\') {
            escaping = true;
        } else if (c == '"') {
            break;
        } else {
            value += c;
        }
    }
    return value;
}

std::string extract_object_block(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    std::size_t pos = json.find(needle);
    if (pos == std::string::npos) {
        return "";
    }
    pos = json.find('{', pos + needle.size());
    if (pos == std::string::npos) {
        return "";
    }
    int depth = 0;
    bool in_string = false;
    bool escaping = false;
    for (std::size_t i = pos; i < json.size(); ++i) {
        const char c = json[i];
        if (escaping) {
            escaping = false;
            continue;
        }
        if (c == '\\') {
            escaping = true;
            continue;
        }
        if (c == '"') {
            in_string = !in_string;
            continue;
        }
        if (in_string) {
            continue;
        }
        if (c == '{') {
            ++depth;
        } else if (c == '}') {
            --depth;
            if (depth == 0) {
                return json.substr(pos, i - pos + 1);
            }
        }
    }
    return "";
}

std::string extract_array_block(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    std::size_t pos = json.find(needle);
    if (pos == std::string::npos) {
        return "";
    }
    pos = json.find('[', pos + needle.size());
    if (pos == std::string::npos) {
        return "";
    }
    int depth = 0;
    bool in_string = false;
    bool escaping = false;
    for (std::size_t i = pos; i < json.size(); ++i) {
        const char c = json[i];
        if (escaping) {
            escaping = false;
            continue;
        }
        if (c == '\\') {
            escaping = true;
            continue;
        }
        if (c == '"') {
            in_string = !in_string;
            continue;
        }
        if (in_string) {
            continue;
        }
        if (c == '[') {
            ++depth;
        } else if (c == ']') {
            --depth;
            if (depth == 0) {
                return json.substr(pos, i - pos + 1);
            }
        }
    }
    return "";
}

std::string extract_json_scalar(const std::string& json, const std::string& key, const std::string& fallback) {
    const std::string needle = "\"" + key + "\"";
    std::size_t pos = json.find(needle);
    if (pos == std::string::npos) {
        return fallback;
    }
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) {
        return fallback;
    }
    ++pos;
    while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {
        ++pos;
    }
    if (pos >= json.size()) {
        return fallback;
    }
    if (json[pos] == '[') {
        const std::string arr = extract_array_block(json.substr(0, json.size()), key);
        return arr.empty() ? fallback : arr;
    }
    std::size_t end = pos;
    while (end < json.size() && json[end] != ',' && json[end] != '}' && json[end] != ']') {
        ++end;
    }
    std::string value = json.substr(pos, end - pos);
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) {
        value.pop_back();
    }
    return value.empty() ? fallback : value;
}

WorkerConfig parse_worker_config(const std::string& config_path, const std::string& config_json) {
    WorkerConfig config;
    config.config_path = config_path;
    config.config_dir = dirname_of(config_path);
    config.worker_id = extract_json_string(config_json, "worker_id");
    config.dsm_base_url = extract_json_string(config_json, "dsm_base_url");
    config.workspace_root = extract_json_string(config_json, "workspace_root");
    config.poll_interval_seconds = parse_int(extract_json_scalar(config_json, "poll_interval_seconds", "2"), 2);
    if (config.poll_interval_seconds < 1) {
        config.poll_interval_seconds = 1;
    }

    const std::string processors = extract_object_block(config_json, "processors");
    const std::string face = extract_object_block(processors.empty() ? config_json : processors, "face");
    config.face_path = extract_json_string(face.empty() ? config_json : face, "path");
    config.face_model_root = extract_json_string(face.empty() ? config_json : face, "model_root");
    config.face_model_name = extract_json_string(face.empty() ? config_json : face, "model_name");

    config.face_path = join_path(config.config_dir, config.face_path);
    config.face_model_root = join_path(config.config_dir, config.face_model_root);
    config.workspace_root = join_path(config.config_dir, config.workspace_root);
    return config;
}

FaceModelStatus inspect_face_models(const WorkerConfig& config) {
    FaceModelStatus status;
    status.model_dir = join_path(config.face_model_root, config.face_model_name);
    status.detector_path = join_path(status.model_dir, "det_10g.onnx");
    status.recognizer_path = join_path(status.model_dir, "w600k_r50.onnx");
    status.manifest_path = join_path(status.model_dir, "manifest.json");
    status.license_ack_path = join_path(status.model_dir, "LICENSE_ACK.json");
    status.detector_present = file_exists(status.detector_path);
    status.recognizer_present = file_exists(status.recognizer_path);
    status.manifest_present = file_exists(status.manifest_path);
    status.license_ack_present = file_exists(status.license_ack_path);
    return status;
}

bool face_models_present(const FaceModelStatus& status) {
    return status.detector_present && status.recognizer_present;
}

std::string missing_model_message(const FaceModelStatus& status) {
    std::ostringstream out;
    out << "model_missing: expected detector=" << status.detector_path
        << ", recognizer=" << status.recognizer_path;
    return out.str();
}

std::string face_command_from_type(const std::string& type) {
    if (type == "face_native_detect") return "detect";
    if (type == "face_native_embed") return "embed";
    if (type == "face_native_detect_batch") return "detect_batch";
    if (type == "face_native_embed_batch") return "embed_batch";
    if (type == "face_native_rank_embeddings") return "rank_embeddings";
    if (type == "face_native_profile_math") return "profile_math";
    return "";
}

std::string resolve_job_image_path(const std::string& job_json, const std::string& job_dir) {
    std::string image_path = extract_json_string(job_json, "image_path");
    if (image_path.empty()) {
        image_path = extract_json_string(job_json, "local_path");
    }
    return join_path(job_dir, image_path);
}

std::string build_processor_payload(const std::string& job_json, const std::string& job_path, const WorkerConfig& config, const std::string& type, const std::string& command) {
    const std::string job_id = extract_json_string(job_json, "job_id").empty() ? "local" : extract_json_string(job_json, "job_id");
    const std::string job_dir = dirname_of(job_path);
    const std::string image_path = resolve_job_image_path(job_json, job_dir);
    const std::string min_confidence = extract_json_scalar(job_json, "min_confidence", "0.5");
    const std::string max_faces = extract_json_scalar(job_json, "max_faces", "0");
    const std::string det_size = extract_json_scalar(job_json, "det_size", "[640,640]");
    const std::string image_paths = extract_array_block(job_json, "image_paths");

    std::ostringstream payload;
    payload << "{" << "\"contract_version\":\"1.0\",";
    payload << "\"job_id\":\"" << json_escape(job_id) << "\",";
    payload << "\"type\":\"" << json_escape(type) << "\",";
    if (command == "detect_batch" || command == "embed_batch") {
        payload << "\"image_paths\":" << (image_paths.empty() ? "[]" : image_paths) << ",";
    } else {
        payload << "\"image_path\":\"" << json_escape(image_path) << "\",";
        payload << "\"input\":{\"image_path\":\"" << json_escape(image_path) << "\",\"source_id\":\"" << json_escape(image_path) << "\"},";
    }
    payload << "\"model_root\":\"" << json_escape(config.face_model_root) << "\",";
    payload << "\"model_name\":\"" << json_escape(config.face_model_name) << "\",";
    payload << "\"min_confidence\":" << min_confidence << ",";
    payload << "\"max_faces\":" << max_faces << ",";
    payload << "\"det_size\":" << det_size << ",";
    payload << "\"options\":{"
            << "\"model_root\":\"" << json_escape(config.face_model_root) << "\",";
    payload << "\"model_name\":\"" << json_escape(config.face_model_name) << "\",";
    payload << "\"min_confidence\":" << min_confidence << ",";
    payload << "\"max_faces\":" << max_faces << ",";
    payload << "\"det_size\":" << det_size << ",";
    payload << "\"normalize_coordinates\":true}";
    payload << "}";
    return payload.str();
}

bool load_config_from_args(const std::vector<std::string>& args, WorkerConfig* config, std::string* config_json) {
    const std::string config_path = arg_value(args, "--config");
    if (config_path.empty()) {
        std::cerr << "ERROR: --config is required\n";
        return false;
    }
    if (!file_exists(config_path)) {
        std::cerr << "ERROR: config file not found: " << config_path << "\n";
        return false;
    }
    *config_json = read_file(config_path);
    *config = parse_worker_config(config_path, *config_json);
    return true;
}

struct ReadinessStatus {
    bool has_worker_id = false;
    bool has_processors = false;
    bool has_face = false;
    bool face_binary_exists = false;
    bool models_present = false;
    bool face_version_ok = false;
    bool face_probe_ok = false;
    FaceModelStatus model_status;
    CommandResult face_version;
    CommandResult face_probe;
};

ReadinessStatus check_readiness(const WorkerConfig& config, const std::string& config_json) {
    ReadinessStatus status;
    status.model_status = inspect_face_models(config);
    status.models_present = face_models_present(status.model_status);
    status.has_worker_id = !config.worker_id.empty();
    status.has_processors = config_json.find("\"processors\"") != std::string::npos;
    status.has_face = !config.face_path.empty();
    status.face_binary_exists = file_exists(config.face_path);
    if (status.face_binary_exists) {
        status.face_version = run_processor_capture(config.face_path, {"version"});
        status.face_version_ok = status.face_version.exit_code == 0;
        if (status.models_present) {
            status.face_probe = run_processor_capture(config.face_path, {"probe", "--model-root", config.face_model_root, "--model-name", config.face_model_name});
            status.face_probe_ok = status.face_probe.exit_code == 0;
        } else {
            status.face_probe.exit_code = 5;
            status.face_probe.output = missing_model_message(status.model_status);
        }
    }
    return status;
}

bool ready_for_face_jobs(const ReadinessStatus& status) {
    return status.has_worker_id && status.has_processors && status.has_face && status.face_binary_exists && status.models_present && status.face_version_ok && status.face_probe_ok;
}

void print_capabilities(bool ready) {
    if (!ready) {
        return;
    }
    std::cout
        << "\"face_native_detect\", "
        << "\"face_native_embed\", "
        << "\"face_native_detect_batch\", "
        << "\"face_native_embed_batch\", "
        << "\"face_native_rank_embeddings\", "
        << "\"face_native_profile_math\", "
        << "\"warm_processor_worker\"";
}

int print_usage() {
    std::cout
        << "av-imgdata-worker " << AV_IMGDATA_WORKER_VERSION << "\n"
        << "\n"
        << "Usage:\n"
        << "  av-imgdata-worker version\n"
        << "  av-imgdata-worker probe --config <worker-config.json>\n"
        << "  av-imgdata-worker once --config <worker-config.json> --job <job.json>\n"
        << "  av-imgdata-worker run --config <worker-config.json> [--max-iterations <n>]\n"
        << "\n"
        << "Phase D status:\n"
        << "  Local readiness loop for the future DSM Worker API. Remote job polling is still disabled.\n";
    return 0;
}

int command_version() {
    std::cout << "av-imgdata-worker " << AV_IMGDATA_WORKER_VERSION << "\n";
    return 0;
}

int command_probe(const std::vector<std::string>& args) {
    WorkerConfig config;
    std::string config_json;
    if (!load_config_from_args(args, &config, &config_json)) {
        return 2;
    }
    const ReadinessStatus status = check_readiness(config, config_json);
    const bool ready = ready_for_face_jobs(status);

    std::cout
        << "{\n"
        << "  \"worker\": {\"name\": \"av-imgdata-worker\", \"version\": \"" << AV_IMGDATA_WORKER_VERSION << "\"},\n"
        << "  \"phase\": \"D\",\n"
        << "  \"config\": {\n"
        << "    \"path\": \"" << json_escape(config.config_path) << "\",\n"
        << "    \"readable\": true,\n"
        << "    \"worker_id\": \"" << json_escape(config.worker_id) << "\",\n"
        << "    \"dsm_base_url\": \"" << json_escape(config.dsm_base_url) << "\",\n"
        << "    \"workspace_root\": \"" << json_escape(config.workspace_root) << "\",\n"
        << "    \"poll_interval_seconds\": " << config.poll_interval_seconds << "\n"
        << "  },\n"
        << "  \"checks\": {\n"
        << "    \"worker_id_present\": " << (status.has_worker_id ? "true" : "false") << ",\n"
        << "    \"processors_present\": " << (status.has_processors ? "true" : "false") << ",\n"
        << "    \"face_processor_config_present\": " << (status.has_face ? "true" : "false") << ",\n"
        << "    \"face_processor_binary_exists\": " << (status.face_binary_exists ? "true" : "false") << ",\n"
        << "    \"face_models_present\": " << (status.models_present ? "true" : "false") << ",\n"
        << "    \"face_model_manifest_present\": " << (status.model_status.manifest_present ? "true" : "false") << ",\n"
        << "    \"face_model_license_ack_present\": " << (status.model_status.license_ack_present ? "true" : "false") << "\n"
        << "  },\n"
        << "  \"processors\": [\n"
        << "    {\n"
        << "      \"name\": \"av-imgdata-face-processor\",\n"
        << "      \"path\": \"" << json_escape(config.face_path) << "\",\n"
        << "      \"model_root\": \"" << json_escape(config.face_model_root) << "\",\n"
        << "      \"model_name\": \"" << json_escape(config.face_model_name) << "\",\n"
        << "      \"binary_exists\": " << (status.face_binary_exists ? "true" : "false") << ",\n"
        << "      \"version_ok\": " << (status.face_version_ok ? "true" : "false") << ",\n"
        << "      \"version_output\": \"" << json_escape(status.face_version.output) << "\",\n"
        << "      \"models\": {\n"
        << "        \"managed_by\": \"dsm_or_manual\",\n"
        << "        \"distributed_with_worker\": false,\n"
        << "        \"usage_ack_required\": true,\n"
        << "        \"model_dir\": \"" << json_escape(status.model_status.model_dir) << "\",\n"
        << "        \"detector_path\": \"" << json_escape(status.model_status.detector_path) << "\",\n"
        << "        \"recognizer_path\": \"" << json_escape(status.model_status.recognizer_path) << "\",\n"
        << "        \"manifest_path\": \"" << json_escape(status.model_status.manifest_path) << "\",\n"
        << "        \"license_ack_path\": \"" << json_escape(status.model_status.license_ack_path) << "\",\n"
        << "        \"detector_present\": " << (status.model_status.detector_present ? "true" : "false") << ",\n"
        << "        \"recognizer_present\": " << (status.model_status.recognizer_present ? "true" : "false") << ",\n"
        << "        \"models_present\": " << (status.models_present ? "true" : "false") << ",\n"
        << "        \"manifest_present\": " << (status.model_status.manifest_present ? "true" : "false") << ",\n"
        << "        \"license_ack_present\": " << (status.model_status.license_ack_present ? "true" : "false") << "\n"
        << "      },\n"
        << "      \"probe_ok\": " << (status.face_probe_ok ? "true" : "false") << ",\n"
        << "      \"probe_output\": \"" << json_escape(status.face_probe.output) << "\"\n"
        << "    }\n"
        << "  ],\n"
        << "  \"capabilities\": [";
    print_capabilities(ready);
    std::cout
        << "],\n"
        << "  \"remote_api\": {\n"
        << "    \"status\": \"planned\",\n"
        << "    \"run_loop_ready\": true,\n"
        << "    \"job_polling\": \"not_implemented\",\n"
        << "    \"planned_model_source\": \"dsm_package_model_store_after_license_ack\"\n"
        << "  }\n"
        << "}\n";

    return status.has_worker_id && status.has_processors && status.has_face ? 0 : 4;
}

int command_once(const std::vector<std::string>& args) {
    const std::string config_path = arg_value(args, "--config");
    const std::string job_path = arg_value(args, "--job");
    if (config_path.empty() || job_path.empty()) {
        std::cerr << "ERROR: --config and --job are required\n";
        return 2;
    }
    if (!file_exists(config_path)) {
        std::cerr << "ERROR: config file not found: " << config_path << "\n";
        return 3;
    }
    if (!file_exists(job_path)) {
        std::cerr << "ERROR: job file not found: " << job_path << "\n";
        return 3;
    }

    const std::string config_json = read_file(config_path);
    const WorkerConfig config = parse_worker_config(config_path, config_json);
    const std::string job = read_file(job_path);
    const std::string job_id = extract_json_string(job, "job_id").empty() ? "local" : extract_json_string(job, "job_id");
    const std::string type = extract_json_string(job, "type");
    const std::string processor_command = face_command_from_type(type);
    const bool has_job_id = job.find("job_id") != std::string::npos;
    const bool has_type = !type.empty();
    const bool face_binary_exists = file_exists(config.face_path);
    const FaceModelStatus model_status = inspect_face_models(config);
    const bool models_present = face_models_present(model_status);
    const std::string job_dir = dirname_of(job_path);
    const std::string safe_job_name = basename_of(job_path);
    const std::string processor_input = join_path(job_dir, safe_job_name + ".processor-input.json");
    const std::string processor_output = join_path(job_dir, safe_job_name + ".processor-result.json");

    CommandResult processor_result;
    std::string processor_output_json;
    std::string processor_execution = "not_started";
    std::string error_code;
    std::string error_message;

    if (processor_command.empty()) {
        processor_execution = "unsupported_job_type";
        error_code = "unsupported_job_type";
        error_message = "unsupported or missing job type";
    } else if (!face_binary_exists) {
        processor_execution = "blocked";
        error_code = "face_processor_missing";
        error_message = "face processor binary is missing";
    } else if (!models_present) {
        processor_execution = "blocked";
        error_code = "face_models_missing";
        error_message = missing_model_message(model_status);
    } else {
        const std::string payload = build_processor_payload(job, job_path, config, type, processor_command);
        if (!write_file(processor_input, payload)) {
            processor_execution = "failed";
            error_code = "input_write_failed";
            error_message = processor_input;
        } else {
            processor_result = run_processor_capture(config.face_path, {processor_command, "--input", processor_input, "--output", processor_output});
            processor_output_json = read_file(processor_output);
            processor_execution = processor_result.exit_code == 0 ? "completed" : "failed";
            if (processor_result.exit_code != 0) {
                error_code = "processor_failed";
                error_message = processor_result.output;
            }
        }
    }

    std::cout
        << "{\n"
        << "  \"worker\": {\"name\": \"av-imgdata-worker\", \"version\": \"" << AV_IMGDATA_WORKER_VERSION << "\"},\n"
        << "  \"phase\": \"D\",\n"
        << "  \"mode\": \"once\",\n"
        << "  \"config_path\": \"" << json_escape(config_path) << "\",\n"
        << "  \"job_path\": \"" << json_escape(job_path) << "\",\n"
        << "  \"checks\": {\"job_id_present\": " << (has_job_id ? "true" : "false")
        << ", \"type_present\": " << (has_type ? "true" : "false")
        << ", \"face_processor_binary_exists\": " << (face_binary_exists ? "true" : "false")
        << ", \"face_models_present\": " << (models_present ? "true" : "false") << "},\n"
        << "  \"job\": {\"job_id\": \"" << json_escape(job_id) << "\", \"type\": \"" << json_escape(type) << "\", \"processor_command\": \"" << json_escape(processor_command) << "\"},\n"
        << "  \"processor_execution\": \"" << json_escape(processor_execution) << "\",\n"
        << "  \"processor\": {\"path\": \"" << json_escape(config.face_path) << "\", \"exit_code\": " << processor_result.exit_code << ", \"output\": \"" << json_escape(processor_result.output) << "\"},\n"
        << "  \"artifacts\": {\"processor_input\": \"" << json_escape(processor_input) << "\", \"processor_result\": \"" << json_escape(processor_output) << "\"}";
    if (!processor_output_json.empty() && processor_output_json.find('{') != std::string::npos) {
        std::cout << ",\n  \"processor_result\": " << processor_output_json;
    }
    if (!error_code.empty()) {
        std::cout << ",\n  \"error\": {\"code\": \"" << json_escape(error_code) << "\", \"message\": \"" << json_escape(error_message) << "\"}";
    }
    std::cout << "\n}\n";
    return processor_execution == "completed" ? 0 : 4;
}

int command_run(const std::vector<std::string>& args) {
    WorkerConfig config;
    std::string config_json;
    if (!load_config_from_args(args, &config, &config_json)) {
        return 2;
    }
    const int max_iterations = parse_int(arg_value(args, "--max-iterations"), 0);
    int iteration = 0;
    while (max_iterations <= 0 || iteration < max_iterations) {
        ++iteration;
        const ReadinessStatus status = check_readiness(config, config_json);
        const bool ready = ready_for_face_jobs(status);
        std::cout
            << "{\"worker\":{\"name\":\"av-imgdata-worker\",\"version\":\"" << AV_IMGDATA_WORKER_VERSION << "\"}"
            << ",\"phase\":\"D\""
            << ",\"mode\":\"run\""
            << ",\"iteration\":" << iteration
            << ",\"worker_id\":\"" << json_escape(config.worker_id) << "\""
            << ",\"ready\":" << (ready ? "true" : "false")
            << ",\"dsm_base_url\":\"" << json_escape(config.dsm_base_url) << "\""
            << ",\"poll_interval_seconds\":" << config.poll_interval_seconds
            << ",\"job_polling\":\"not_implemented\""
            << ",\"checks\":{\"face_processor_binary_exists\":" << (status.face_binary_exists ? "true" : "false")
            << ",\"face_models_present\":" << (status.models_present ? "true" : "false")
            << ",\"face_probe_ok\":" << (status.face_probe_ok ? "true" : "false")
            << ",\"license_ack_present\":" << (status.model_status.license_ack_present ? "true" : "false")
            << "}}" << std::endl;
        if (max_iterations > 0 && iteration >= max_iterations) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::seconds(config.poll_interval_seconds));
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) {
        args.push_back(argv[i]);
    }
    if (args.empty() || has_arg(args, "--help") || has_arg(args, "-h")) {
        return print_usage();
    }
    const std::string command = args[0];
    if (command == "version") {
        return command_version();
    }
    if (command == "probe") {
        return command_probe(args);
    }
    if (command == "once") {
        return command_once(args);
    }
    if (command == "run") {
        return command_run(args);
    }
    std::cerr << "ERROR: unknown command: " << command << "\n";
    return print_usage() == 0 ? 2 : 2;
}
