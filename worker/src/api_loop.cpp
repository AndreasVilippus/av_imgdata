#include <array>
#include <cctype>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <direct.h>
#define POPEN _popen
#define PCLOSE _pclose
#define GETCWD _getcwd
#else
#include <unistd.h>
#define POPEN popen
#define PCLOSE pclose
#define GETCWD getcwd
#endif

#ifndef AV_IMGDATA_WORKER_VERSION
#define AV_IMGDATA_WORKER_VERSION "0.1.0-phase-e"
#endif

namespace {

struct CommandResult {
    int exit_code = -1;
    std::string output;
};

struct LoopConfig {
    std::string config_path;
    std::string config_dir;
    std::string worker_id;
    std::string worker_bin;
    std::string api_url;
    std::string token_file;
    std::string workspace_root;
    std::string path_base_dir;
    int poll_interval_seconds = 2;
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
    for (const std::string& arg : args) {
        if (arg == name) {
            return true;
        }
    }
    return false;
}

int parse_int(const std::string& value, int fallback) {
    if (value.empty()) {
        return fallback;
    }
    char* end = nullptr;
    const long parsed = std::strtol(value.c_str(), &end, 10);
    if (end == value.c_str()) {
        return fallback;
    }
    return static_cast<int>(parsed);
}

int normalized_exit_code(int raw) {
#ifndef _WIN32
    if (raw >= 256 && raw % 256 == 0) {
        return raw / 256;
    }
#endif
    return raw;
}

bool is_path_separator(char c) {
    return c == '/' || c == '\\';
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

std::string current_working_dir() {
    std::array<char, 4096> buffer{};
    if (GETCWD(buffer.data(), static_cast<int>(buffer.size())) == nullptr) {
        return ".";
    }
    return buffer.data();
}

char preferred_separator_for(const std::string& path) {
#ifdef _WIN32
    (void)path;
    return '\\';
#else
    return path.find('\\') != std::string::npos ? '\\' : '/';
#endif
}

std::string normalize_path_lexically(const std::string& path) {
    if (path.empty()) {
        return path;
    }

    const char sep = preferred_separator_for(path);
    std::string normalized = path;
    for (char& c : normalized) {
        if (is_path_separator(c)) {
            c = sep;
        }
    }

    std::string prefix;
    std::size_t pos = 0;
    bool absolute = false;

    if (normalized.size() >= 2 && normalized[1] == ':') {
        prefix = normalized.substr(0, 2);
        pos = 2;
        if (pos < normalized.size() && normalized[pos] == sep) {
            prefix += sep;
            ++pos;
            absolute = true;
        }
    } else if (normalized.size() >= 2 && normalized[0] == sep && normalized[1] == sep) {
        prefix = std::string(2, sep);
        pos = 2;
        absolute = true;
    } else if (normalized[0] == sep) {
        prefix = std::string(1, sep);
        pos = 1;
        absolute = true;
    }

    std::vector<std::string> parts;
    while (pos <= normalized.size()) {
        const std::size_t next = normalized.find(sep, pos);
        const std::string part = normalized.substr(pos, next == std::string::npos ? std::string::npos : next - pos);
        if (part.empty() || part == ".") {
            // skip
        } else if (part == "..") {
            if (!parts.empty() && parts.back() != "..") {
                parts.pop_back();
            } else if (!absolute) {
                parts.push_back(part);
            }
        } else {
            parts.push_back(part);
        }
        if (next == std::string::npos) {
            break;
        }
        pos = next + 1;
    }

    std::string output = prefix;
    for (std::size_t i = 0; i < parts.size(); ++i) {
        if (!output.empty() && output.back() != sep) {
            output += sep;
        }
        output += parts[i];
    }
    if (output.empty()) {
        return ".";
    }
    return output;
}

std::string absolute_path(const std::string& path) {
    if (path.empty()) {
        return path;
    }
    if (looks_absolute(path)) {
        return normalize_path_lexically(path);
    }
    return normalize_path_lexically(join_path(current_working_dir(), path));
}

bool file_exists(const std::string& path) {
    if (path.empty()) {
        return false;
    }
    std::ifstream input(path.c_str(), std::ios::binary);
    return static_cast<bool>(input);
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

bool ensure_dir(const std::string& path) {
    if (path.empty()) {
        return false;
    }
#ifdef _WIN32
    std::string command = "mkdir " + shell_quote(normalize_path_lexically(path)) + " >NUL 2>NUL";
#else
    std::string command = "mkdir -p " + shell_quote(normalize_path_lexically(path));
#endif
    return std::system(command.c_str()) == 0;
}

std::string read_file(const std::string& path) {
    std::ifstream input(path.c_str(), std::ios::binary);
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

bool write_file(const std::string& path, const std::string& text) {
    ensure_dir(dirname_of(path));
    std::ofstream output(path.c_str(), std::ios::binary);
    if (!output) {
        return false;
    }
    output << text;
    return static_cast<bool>(output);
}

std::string trim(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) {
        value.pop_back();
    }
    std::size_t start = 0;
    while (start < value.size() && std::isspace(static_cast<unsigned char>(value[start]))) {
        ++start;
    }
    if (start > 0) {
        value.erase(0, start);
    }
    return value;
}

std::string abbreviate(const std::string& value, std::size_t max_len) {
    if (value.size() <= max_len) {
        return value;
    }
    if (max_len <= 3) {
        return value.substr(0, max_len);
    }
    return value.substr(0, max_len - 3) + "...";
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

CommandResult run_command_capture(const std::string& command) {
    CommandResult result;
    std::array<char, 512> buffer{};
    FILE* pipe = POPEN(command.c_str(), "r");
    if (!pipe) {
        result.output = "popen_failed";
        return result;
    }
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        result.output += buffer.data();
    }
    result.exit_code = PCLOSE(pipe);
    result.output = trim(result.output);
    return result;
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

std::string extract_block_after_key(const std::string& json, const std::string& key, char open_char, char close_char) {
    const std::string needle = "\"" + key + "\"";
    std::size_t pos = json.find(needle);
    if (pos == std::string::npos) {
        return "";
    }
    pos = json.find(open_char, pos + needle.size());
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
        if (c == open_char) {
            ++depth;
        } else if (c == close_char) {
            --depth;
            if (depth == 0) {
                return json.substr(pos, i - pos + 1);
            }
        }
    }
    return "";
}

std::string extract_object_block(const std::string& json, const std::string& key) {
    return extract_block_after_key(json, key, '{', '}');
}

std::string normalize_base_url(std::string url) {
    while (!url.empty() && url.back() == '/') {
        url.pop_back();
    }
    return url;
}

std::string read_token(const std::string& token_file) {
    return trim(read_file(token_file));
}

std::string normalize_job_path_value(const std::string& base_dir, const std::string& value) {
    if (value.empty() || looks_absolute(value)) {
        return normalize_path_lexically(value);
    }
    return normalize_path_lexically(join_path(base_dir, value));
}

bool replace_json_string_value(std::string* json, const std::string& key, const std::string& base_dir) {
    const std::string needle = "\"" + key + "\"";
    std::size_t pos = json->find(needle);
    if (pos == std::string::npos) {
        return false;
    }
    pos = json->find(':', pos + needle.size());
    if (pos == std::string::npos) {
        return false;
    }
    std::size_t quote = json->find('"', pos + 1);
    if (quote == std::string::npos) {
        return false;
    }
    std::size_t end = quote + 1;
    bool escaping = false;
    for (; end < json->size(); ++end) {
        const char c = (*json)[end];
        if (escaping) {
            escaping = false;
        } else if (c == '\\') {
            escaping = true;
        } else if (c == '"') {
            break;
        }
    }
    if (end >= json->size()) {
        return false;
    }
    const std::string old_value = json->substr(quote + 1, end - quote - 1);
    const std::string new_value = normalize_job_path_value(base_dir, old_value);
    json->replace(quote + 1, end - quote - 1, json_escape(new_value));
    return true;
}

std::string normalize_payload_paths(std::string payload, const std::string& base_dir) {
    replace_json_string_value(&payload, "local_path", base_dir);
    replace_json_string_value(&payload, "image_path", base_dir);
    return payload;
}

LoopConfig parse_config(const std::string& config_path, const std::string& config_json, const std::vector<std::string>& args) {
    LoopConfig config;
    config.config_path = absolute_path(config_path);
    config.config_dir = dirname_of(config.config_path);
    config.worker_id = extract_json_string(config_json, "worker_id");
    config.workspace_root = absolute_path(join_path(config.config_dir, extract_json_string(config_json, "workspace_root")));
    config.path_base_dir = arg_value(args, "--path-base-dir");
    if (config.path_base_dir.empty()) {
        config.path_base_dir = current_working_dir();
    }
    config.path_base_dir = absolute_path(config.path_base_dir);
    config.poll_interval_seconds = parse_int(extract_json_string(config_json, "poll_interval_seconds"), 2);
    if (config.poll_interval_seconds < 1) {
        config.poll_interval_seconds = 1;
    }

    const std::string auth = extract_object_block(config_json, "auth");
    config.token_file = extract_json_string(auth.empty() ? config_json : auth, "token_file");
    config.token_file = absolute_path(join_path(config.config_dir, config.token_file.empty() ? "../worker.token" : config.token_file));

    config.api_url = arg_value(args, "--api-url");
    if (config.api_url.empty()) {
        config.api_url = extract_json_string(config_json, "worker_api_base_url");
    }
    if (config.api_url.empty()) {
        const std::string dsm_base_url = extract_json_string(config_json, "dsm_base_url");
        if (!dsm_base_url.empty()) {
            config.api_url = normalize_base_url(dsm_base_url) + "/worker-api";
        }
    }
    config.api_url = normalize_base_url(config.api_url);

    config.worker_bin = arg_value(args, "--worker-bin");
    if (config.worker_bin.empty()) {
#ifdef _WIN32
        config.worker_bin = join_path(config.config_dir, "../bin/av-imgdata-worker.exe");
#else
        config.worker_bin = join_path(config.config_dir, "../bin/av-imgdata-worker");
#endif
    }
    config.worker_bin = absolute_path(config.worker_bin);
    return config;
}

std::string capabilities_json() {
    return "[\"face_native_detect\",\"face_native_embed\",\"face_native_detect_batch\",\"face_native_embed_batch\",\"face_native_rank_embeddings\",\"face_native_profile_math\",\"warm_processor_worker\"]";
}

std::string api_post_payload(const LoopConfig& config, const std::string& action, const std::string& token, const std::string& body) {
    const std::string body_path = normalize_path_lexically(join_path(config.workspace_root, ".api-" + action + "-request.json"));
    write_file(body_path, body);
    const std::string url = config.api_url + "/" + action;
    std::string command = "curl -sS -X POST";
    command += " -H " + shell_quote("Content-Type: application/json");
    command += " -H " + shell_quote("Authorization: Bearer " + token);
    command += " --data-binary @" + shell_quote(body_path);
    command += " " + shell_quote(url);
    command += " 2>&1";
    CommandResult result = run_command_capture(command);
    if (normalized_exit_code(result.exit_code) != 0) {
        return "{\"status\":\"error\",\"code\":\"curl_failed\",\"message\":\"" + json_escape(result.output) + "\"}";
    }
    return result.output;
}

std::string heartbeat_body(const LoopConfig& config, const std::string& status) {
    std::ostringstream body;
    body << "{\"worker_id\":\"" << json_escape(config.worker_id) << "\",";
    body << "\"version\":\"" << AV_IMGDATA_WORKER_VERSION << "\",";
    body << "\"status\":\"" << json_escape(status) << "\",";
    body << "\"capabilities\":" << capabilities_json() << ",";
    body << "\"metadata\":{\"runtime\":\"cxx-api-loop\",\"path_base_dir\":\"" << json_escape(config.path_base_dir) << "\"}}";
    return body.str();
}

std::string claim_body(const LoopConfig& config) {
    std::ostringstream body;
    body << "{\"worker_id\":\"" << json_escape(config.worker_id) << "\",";
    body << "\"capabilities\":" << capabilities_json() << "}";
    return body.str();
}

std::string claimed_job_to_local_job(const std::string& claimed_job, const std::string& path_base_dir) {
    const std::string payload = normalize_payload_paths(extract_object_block(claimed_job, "payload"), path_base_dir);
    const std::string job_id = extract_json_string(claimed_job, "job_id");
    const std::string type = extract_json_string(claimed_job, "type");
    std::ostringstream job;
    job << "{\"job_id\":\"" << json_escape(job_id) << "\",\"type\":\"" << json_escape(type) << "\"";
    if (!payload.empty() && payload.size() >= 2) {
        const std::string inner = payload.substr(1, payload.size() - 2);
        if (!trim(inner).empty()) {
            job << "," << inner;
        }
    }
    job << "}";
    return job.str();
}

CommandResult run_worker_once(const LoopConfig& config, const std::string& job_path) {
    std::string command = shell_quote(config.worker_bin);
    command += " once --config " + shell_quote(config.config_path);
    command += " --job " + shell_quote(normalize_path_lexically(job_path));
    command += " 2>&1";
    return run_command_capture(command);
}

std::string result_body(const LoopConfig& config, const std::string& job_id, const std::string& worker_result) {
    std::ostringstream body;
    body << "{\"worker_id\":\"" << json_escape(config.worker_id) << "\",";
    body << "\"job_id\":\"" << json_escape(job_id) << "\",";
    body << "\"result\":" << (worker_result.empty() ? "{}" : worker_result) << "}";
    return body.str();
}

std::string fail_body(const LoopConfig& config, const std::string& job_id, const std::string& code, const std::string& message, const std::string& detail_json) {
    std::ostringstream body;
    body << "{\"worker_id\":\"" << json_escape(config.worker_id) << "\",";
    body << "\"job_id\":\"" << json_escape(job_id) << "\",";
    body << "\"error\":{\"code\":\"" << json_escape(code) << "\",\"message\":\"" << json_escape(message) << "\"";
    if (!detail_json.empty() && detail_json.find('{') != std::string::npos) {
        body << ",\"worker_result\":" << detail_json;
    }
    body << "}}";
    return body.str();
}

bool is_worker_success(const CommandResult& result) {
    return normalized_exit_code(result.exit_code) == 0 && result.output.find("\"processor_execution\": \"completed\"") != std::string::npos;
}

int print_usage() {
    std::cout
        << "av-imgdata-worker-api-loop " << AV_IMGDATA_WORKER_VERSION << "\n\n"
        << "Usage:\n"
        << "  av-imgdata-worker-api-loop --config <worker-config.json> [--api-url <url>] [--worker-bin <path>] [--path-base-dir <path>] [--max-iterations <n>]\n\n"
        << "The loop uses curl for HTTP POST calls and av-imgdata-worker once for local job execution.\n";
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
    const LoopConfig config = parse_config(config_path, config_json, args);
    const int max_iterations = parse_int(arg_value(args, "--max-iterations"), 0);

    if (config.worker_id.empty()) {
        std::cerr << "ERROR: worker_id is required in config\n";
        return 4;
    }
    if (config.api_url.empty()) {
        std::cerr << "ERROR: --api-url or worker_api_base_url/dsm_base_url is required\n";
        return 4;
    }
    if (!file_exists(config.token_file)) {
        std::cerr << "ERROR: worker token file not found: " << config.token_file << "\n";
        return 4;
    }
    if (!file_exists(config.worker_bin)) {
        std::cerr << "ERROR: worker binary not found: " << config.worker_bin << "\n";
        return 4;
    }

    const std::string token = read_token(config.token_file);
    ensure_dir(normalize_path_lexically(join_path(config.workspace_root, "claimed-jobs")));

    int iteration = 0;
    while (max_iterations <= 0 || iteration < max_iterations) {
        ++iteration;
        const std::string heartbeat = api_post_payload(config, "heartbeat", token, heartbeat_body(config, "ready"));
        const std::string claim = api_post_payload(config, "claim", token, claim_body(config));
        const std::string claim_status = extract_json_string(claim, "status");

        std::cout << "{\"mode\":\"api-loop\",\"iteration\":" << iteration
                  << ",\"worker_id\":\"" << json_escape(config.worker_id) << "\""
                  << ",\"api_url\":\"" << json_escape(config.api_url) << "\""
                  << ",\"path_base_dir\":\"" << json_escape(config.path_base_dir) << "\""
                  << ",\"heartbeat_status\":\"" << json_escape(extract_json_string(heartbeat, "status")) << "\""
                  << ",\"claim_status\":\"" << json_escape(claim_status) << "\"";

        if (claim_status == "claimed") {
            const std::string claimed_job = extract_object_block(claim, "job");
            const std::string job_id = extract_json_string(claimed_job, "job_id");
            const std::string job_path = normalize_path_lexically(join_path(join_path(config.workspace_root, "claimed-jobs"), job_id + ".json"));
            const std::string local_job = claimed_job_to_local_job(claimed_job, config.path_base_dir);
            write_file(job_path, local_job);
            const CommandResult worker_result = run_worker_once(config, job_path);
            const int exit_code = normalized_exit_code(worker_result.exit_code);
            if (is_worker_success(worker_result)) {
                api_post_payload(config, "result", token, result_body(config, job_id, worker_result.output));
                std::cout << ",\"job_id\":\"" << json_escape(job_id) << "\",\"reported\":\"result\",\"worker_exit_code\":" << exit_code << ",\"worker_raw_status\":" << worker_result.exit_code;
            } else {
                api_post_payload(config, "fail", token, fail_body(config, job_id, "worker_execution_failed", worker_result.output, worker_result.output));
                std::cout << ",\"job_id\":\"" << json_escape(job_id) << "\",\"reported\":\"fail\",\"worker_exit_code\":" << exit_code << ",\"worker_raw_status\":" << worker_result.exit_code << ",\"job_path\":\"" << json_escape(job_path) << "\",\"worker_output_preview\":\"" << json_escape(abbreviate(worker_result.output, 600)) << "\"";
            }
        }
        std::cout << "}" << std::endl;

        if (max_iterations > 0 && iteration >= max_iterations) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::seconds(config.poll_interval_seconds));
    }
    return 0;
}
