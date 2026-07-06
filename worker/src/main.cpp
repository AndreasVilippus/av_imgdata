#include <array>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#ifdef _WIN32
#define POPEN _popen
#define PCLOSE _pclose
#else
#define POPEN popen
#define PCLOSE pclose
#endif

#ifndef AV_IMGDATA_WORKER_VERSION
#define AV_IMGDATA_WORKER_VERSION "0.1.0-phase-b"
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

WorkerConfig parse_worker_config(const std::string& config_path, const std::string& config_json) {
    WorkerConfig config;
    config.config_path = config_path;
    config.config_dir = dirname_of(config_path);
    config.worker_id = extract_json_string(config_json, "worker_id");
    config.dsm_base_url = extract_json_string(config_json, "dsm_base_url");
    config.workspace_root = extract_json_string(config_json, "workspace_root");

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
    const std::string direct_dir = join_path(config.face_model_root, config.face_model_name);
    const std::string nested_dir = join_path(join_path(config.face_model_root, "models"), config.face_model_name);

    status.model_dir = direct_dir;
    status.detector_path = join_path(status.model_dir, "det_10g.onnx");
    status.recognizer_path = join_path(status.model_dir, "w600k_r50.onnx");
    if (!file_exists(status.detector_path) && !file_exists(status.recognizer_path)) {
        status.model_dir = nested_dir;
        status.detector_path = join_path(status.model_dir, "det_10g.onnx");
        status.recognizer_path = join_path(status.model_dir, "w600k_r50.onnx");
    }

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

int print_usage() {
    std::cout
        << "av-imgdata-worker " << AV_IMGDATA_WORKER_VERSION << "\n"
        << "\n"
        << "Usage:\n"
        << "  av-imgdata-worker version\n"
        << "  av-imgdata-worker probe --config <worker-config.json>\n"
        << "  av-imgdata-worker once --config <worker-config.json> --job <job.json>\n"
        << "  av-imgdata-worker run --config <worker-config.json>\n"
        << "\n"
        << "Phase B status:\n"
        << "  Local worker config parsing and native face processor probe. DSM Worker API is not implemented yet.\n";
    return 0;
}

int command_version() {
    std::cout << "av-imgdata-worker " << AV_IMGDATA_WORKER_VERSION << "\n";
    return 0;
}

int command_probe(const std::vector<std::string>& args) {
    const std::string config_path = arg_value(args, "--config");
    if (config_path.empty()) {
        std::cerr << "ERROR: --config is required\n";
        return 2;
    }
    if (!file_exists(config_path)) {
        std::cerr << "ERROR: config file not found: " << config_path << "\n";
        return 3;
    }

    const std::string config_json = read_file(config_path);
    const WorkerConfig config = parse_worker_config(config_path, config_json);
    const FaceModelStatus model_status = inspect_face_models(config);
    const bool models_present = face_models_present(model_status);
    const bool has_worker_id = !config.worker_id.empty();
    const bool has_processors = config_json.find("\"processors\"") != std::string::npos;
    const bool has_face = !config.face_path.empty();
    const bool face_binary_exists = file_exists(config.face_path);

    CommandResult face_version;
    CommandResult face_probe;
    bool face_version_ok = false;
    bool face_probe_ok = false;

    if (face_binary_exists) {
        face_version = run_processor_capture(config.face_path, {"version"});
        face_version_ok = face_version.exit_code == 0;
        if (models_present) {
            face_probe = run_processor_capture(
                config.face_path,
                {"probe", "--model-root", config.face_model_root, "--model-name", config.face_model_name});
            face_probe_ok = face_probe.exit_code == 0;
        } else {
            face_probe.exit_code = 5;
            face_probe.output = missing_model_message(model_status);
        }
    }

    std::cout
        << "{\n"
        << "  \"worker\": {\"name\": \"av-imgdata-worker\", \"version\": \"" << AV_IMGDATA_WORKER_VERSION << "\"},\n"
        << "  \"phase\": \"B\",\n"
        << "  \"config\": {\n"
        << "    \"path\": \"" << json_escape(config.config_path) << "\",\n"
        << "    \"readable\": true,\n"
        << "    \"worker_id\": \"" << json_escape(config.worker_id) << "\",\n"
        << "    \"dsm_base_url\": \"" << json_escape(config.dsm_base_url) << "\",\n"
        << "    \"workspace_root\": \"" << json_escape(config.workspace_root) << "\"\n"
        << "  },\n"
        << "  \"checks\": {\n"
        << "    \"worker_id_present\": " << (has_worker_id ? "true" : "false") << ",\n"
        << "    \"processors_present\": " << (has_processors ? "true" : "false") << ",\n"
        << "    \"face_processor_config_present\": " << (has_face ? "true" : "false") << ",\n"
        << "    \"face_processor_binary_exists\": " << (face_binary_exists ? "true" : "false") << ",\n"
        << "    \"face_models_present\": " << (models_present ? "true" : "false") << ",\n"
        << "    \"face_model_manifest_present\": " << (model_status.manifest_present ? "true" : "false") << ",\n"
        << "    \"face_model_license_ack_present\": " << (model_status.license_ack_present ? "true" : "false") << "\n"
        << "  },\n"
        << "  \"processors\": [\n"
        << "    {\n"
        << "      \"name\": \"av-imgdata-face-processor\",\n"
        << "      \"path\": \"" << json_escape(config.face_path) << "\",\n"
        << "      \"model_root\": \"" << json_escape(config.face_model_root) << "\",\n"
        << "      \"model_name\": \"" << json_escape(config.face_model_name) << "\",\n"
        << "      \"binary_exists\": " << (face_binary_exists ? "true" : "false") << ",\n"
        << "      \"version_ok\": " << (face_version_ok ? "true" : "false") << ",\n"
        << "      \"version_output\": \"" << json_escape(face_version.output) << "\",\n"
        << "      \"models\": {\n"
        << "        \"managed_by\": \"dsm_or_manual\",\n"
        << "        \"distributed_with_worker\": false,\n"
        << "        \"usage_ack_required\": true,\n"
        << "        \"model_dir\": \"" << json_escape(model_status.model_dir) << "\",\n"
        << "        \"detector_path\": \"" << json_escape(model_status.detector_path) << "\",\n"
        << "        \"recognizer_path\": \"" << json_escape(model_status.recognizer_path) << "\",\n"
        << "        \"manifest_path\": \"" << json_escape(model_status.manifest_path) << "\",\n"
        << "        \"license_ack_path\": \"" << json_escape(model_status.license_ack_path) << "\",\n"
        << "        \"detector_present\": " << (model_status.detector_present ? "true" : "false") << ",\n"
        << "        \"recognizer_present\": " << (model_status.recognizer_present ? "true" : "false") << ",\n"
        << "        \"models_present\": " << (models_present ? "true" : "false") << ",\n"
        << "        \"manifest_present\": " << (model_status.manifest_present ? "true" : "false") << ",\n"
        << "        \"license_ack_present\": " << (model_status.license_ack_present ? "true" : "false") << "\n"
        << "      },\n"
        << "      \"probe_ok\": " << (face_probe_ok ? "true" : "false") << ",\n"
        << "      \"probe_output\": \"" << json_escape(face_probe.output) << "\"\n"
        << "    }\n"
        << "  ],\n"
        << "  \"capabilities\": [";

    if (face_version_ok && face_probe_ok && models_present) {
        std::cout
            << "\"face_native_detect\", "
            << "\"face_native_embed\", "
            << "\"face_native_detect_batch\", "
            << "\"face_native_embed_batch\", "
            << "\"face_native_rank_embeddings\", "
            << "\"face_native_profile_math\", "
            << "\"warm_processor_worker\"";
    }

    std::cout
        << "],\n"
        << "  \"remote_api\": " << "{\n"
        << "    \"status\": \"not_implemented\",\n"
        << "    \"planned_model_source\": \"dsm_package_model_store_after_license_ack\"\n"
        << "  }\n"
        << "}\n";

    return has_worker_id && has_processors && has_face ? 0 : 4;
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
    const std::string job = read_file(job_path);
    const bool has_job_id = job.find("job_id") != std::string::npos;
    const bool has_type = job.find("type") != std::string::npos;
    std::cout
        << "{\n"
        << "  \"worker\": {\"name\": \"av-imgdata-worker\", \"version\": \"" << AV_IMGDATA_WORKER_VERSION << "\"},\n"
        << "  \"phase\": \"B\",\n"
        << "  \"mode\": \"once\",\n"
        << "  \"config_path\": \"" << json_escape(config_path) << "\",\n"
        << "  \"job_path\": \"" << json_escape(job_path) << "\",\n"
        << "  \"checks\": {\"job_id_present\": " << (has_job_id ? "true" : "false")
        << ", \"type_present\": " << (has_type ? "true" : "false") << "},\n"
        << "  \"processor_execution\": \"not_implemented\"\n"
        << "}\n";
    return has_job_id && has_type ? 0 : 4;
}

int command_run(const std::vector<std::string>& args) {
    const std::string config_path = arg_value(args, "--config");
    if (config_path.empty()) {
        std::cerr << "ERROR: --config is required\n";
        return 2;
    }
    if (!file_exists(config_path)) {
        std::cerr << "ERROR: config file not found: " << config_path << "\n";
        return 3;
    }
    std::cout
        << "av-imgdata-worker run mode is reserved for the DSM Worker API loop.\n"
        << "Phase B verifies config parsing and local processor probing.\n";
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
