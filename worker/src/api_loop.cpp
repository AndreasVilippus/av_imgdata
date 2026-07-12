#include "av_imgdata/worker_protocol.h"

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

namespace {

struct CommandResult {
    int exit_code = -1;
    std::string output;
    std::string command;
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

struct LocalJobResult {
    bool ok = false;
    std::string job_json;
    std::string code;
    std::string message;
    std::string resolved_path;
};

std::string arg_value(const std::vector<std::string>& args, const std::string& name) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i) {
        if (args[i] == name) return args[i + 1];
    }
    return "";
}

bool has_arg(const std::vector<std::string>& args, const std::string& name) {
    for (const auto& arg : args) if (arg == name) return true;
    return false;
}

int parse_int(const std::string& value, int fallback) {
    if (value.empty()) return fallback;
    char* end = nullptr;
    const long parsed = std::strtol(value.c_str(), &end, 10);
    return end == value.c_str() ? fallback : static_cast<int>(parsed);
}

int normalized_exit_code(int raw) {
#ifndef _WIN32
    if (raw >= 256 && raw % 256 == 0) return raw / 256;
#endif
    return raw;
}

bool is_sep(char c) { return c == '/' || c == '\\'; }

bool looks_absolute(const std::string& path) {
    return !path.empty() && ((path.size() >= 2 && path[1] == ':') || is_sep(path[0]));
}

std::string dirname_of(const std::string& path) {
    const auto pos = path.find_last_of("/\\");
    if (pos == std::string::npos) return ".";
    return pos == 0 ? path.substr(0, 1) : path.substr(0, pos);
}

std::string join_path(const std::string& base, const std::string& path) {
    if (path.empty() || looks_absolute(path)) return path;
    if (base.empty() || base == ".") return path;
#ifdef _WIN32
    const char sep = '\\';
#else
    const char sep = base.find('\\') != std::string::npos ? '\\' : '/';
#endif
    return is_sep(base.back()) ? base + path : base + sep + path;
}

std::string cwd() {
    std::array<char, 4096> buffer{};
    return GETCWD(buffer.data(), static_cast<int>(buffer.size())) ? std::string(buffer.data()) : ".";
}

char preferred_sep(const std::string& path) {
#ifdef _WIN32
    (void)path;
    return '\\';
#else
    return path.find('\\') != std::string::npos ? '\\' : '/';
#endif
}

std::string normalize_path(const std::string& path) {
    if (path.empty()) return path;
    const char sep = preferred_sep(path);
    std::string value = path;
    for (char& c : value) if (is_sep(c)) c = sep;
    std::string prefix;
    std::size_t pos = 0;
    bool absolute = false;
    if (value.size() >= 2 && value[1] == ':') {
        prefix = value.substr(0, 2);
        pos = 2;
        if (pos < value.size() && value[pos] == sep) {
            prefix += sep;
            ++pos;
            absolute = true;
        }
    } else if (value.size() >= 2 && value[0] == sep && value[1] == sep) {
        prefix = std::string(2, sep);
        pos = 2;
        absolute = true;
    } else if (value[0] == sep) {
        prefix = std::string(1, sep);
        pos = 1;
        absolute = true;
    }
    std::vector<std::string> parts;
    while (pos <= value.size()) {
        const auto next = value.find(sep, pos);
        const std::string part = value.substr(pos, next == std::string::npos ? std::string::npos : next - pos);
        if (part.empty() || part == ".") {
        } else if (part == "..") {
            if (!parts.empty() && parts.back() != "..") parts.pop_back();
            else if (!absolute) parts.push_back(part);
        } else {
            parts.push_back(part);
        }
        if (next == std::string::npos) break;
        pos = next + 1;
    }
    std::string out = prefix;
    for (const auto& part : parts) {
        if (!out.empty() && out.back() != sep) out += sep;
        out += part;
    }
    return out.empty() ? "." : out;
}

std::string absolute_path(const std::string& path) {
    return normalize_path(looks_absolute(path) ? path : join_path(cwd(), path));
}

bool file_exists(const std::string& path) {
    std::ifstream file(path.c_str(), std::ios::binary);
    return !path.empty() && static_cast<bool>(file);
}

std::string shell_quote(const std::string& value) {
#ifdef _WIN32
    std::string out = "\"";
    for (char c : value) out += c == '"' ? "\\\"" : std::string(1, c);
    return out + "\"";
#else
    std::string out = "'";
    for (char c : value) out += c == '\'' ? "'\\''" : std::string(1, c);
    return out + "'";
#endif
}

bool ensure_dir(const std::string& path) {
#ifdef _WIN32
    return std::system(("mkdir " + shell_quote(normalize_path(path)) + " >NUL 2>NUL").c_str()) == 0;
#else
    return std::system(("mkdir -p " + shell_quote(normalize_path(path))).c_str()) == 0;
#endif
}

std::string read_file(const std::string& path) {
    std::ifstream in(path.c_str(), std::ios::binary);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

bool write_file(const std::string& path, const std::string& text) {
    ensure_dir(dirname_of(path));
    std::ofstream out(path.c_str(), std::ios::binary);
    out << text;
    return static_cast<bool>(out);
}

std::string trim(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) value.pop_back();
    std::size_t first = 0;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first]))) ++first;
    return value.substr(first);
}

std::string abbreviate(const std::string& value, std::size_t limit) {
    if (value.size() <= limit) return value;
    return value.substr(0, limit > 3 ? limit - 3 : limit) + (limit > 3 ? "..." : "");
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
            default: out << c;
        }
    }
    return out.str();
}

CommandResult run_command(const std::string& command) {
    CommandResult result;
    result.command = command;
    std::array<char, 512> buffer{};
    FILE* pipe = POPEN(command.c_str(), "r");
    if (!pipe) {
        result.output = "popen_failed";
        return result;
    }
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe)) result.output += buffer.data();
    result.exit_code = PCLOSE(pipe);
    result.output = trim(result.output);
    return result;
}

std::string extract_json_string(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return "";
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return "";
    ++pos;
    std::string value;
    bool escaped = false;
    for (; pos < json.size(); ++pos) {
        const char c = json[pos];
        if (escaped) {
            switch (c) {
                case 'n': value += '\n'; break;
                case 'r': value += '\r'; break;
                case 't': value += '\t'; break;
                default: value += c;
            }
            escaped = false;
        } else if (c == '\\') {
            escaped = true;
        } else if (c == '"') {
            break;
        } else {
            value += c;
        }
    }
    return value;
}

std::string extract_block(const std::string& json, const std::string& key, char open, char close) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find(open, pos + needle.size());
    if (pos == std::string::npos) return "";
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    for (std::size_t i = pos; i < json.size(); ++i) {
        const char c = json[i];
        if (escaped) {
            escaped = false;
            continue;
        }
        if (c == '\\') {
            escaped = true;
            continue;
        }
        if (c == '"') {
            in_string = !in_string;
            continue;
        }
        if (in_string) continue;
        if (c == open) ++depth;
        else if (c == close && --depth == 0) return json.substr(pos, i - pos + 1);
    }
    return "";
}

std::string extract_object(const std::string& json, const std::string& key) {
    return extract_block(json, key, '{', '}');
}

std::string normalize_url(std::string url) {
    while (!url.empty() && url.back() == '/') url.pop_back();
    return url;
}

std::string read_token(const std::string& path) { return trim(read_file(path)); }

bool safe_relative_path(const std::string& value, std::string* normalized, std::string* error) {
    if (value.empty()) {
        *error = "local_path_missing";
        return false;
    }
    if (looks_absolute(value)) {
        *error = "local_path_must_be_relative";
        return false;
    }
    std::string portable = value;
    for (char& c : portable) if (c == '\\') c = '/';
    std::vector<std::string> parts;
    std::size_t pos = 0;
    while (pos <= portable.size()) {
        const auto next = portable.find('/', pos);
        const std::string part = portable.substr(pos, next == std::string::npos ? std::string::npos : next - pos);
        if (part.empty() || part == ".") {
        } else if (part == "..") {
            *error = "local_path_escape";
            return false;
        } else {
            parts.push_back(part);
        }
        if (next == std::string::npos) break;
        pos = next + 1;
    }
    if (parts.empty()) {
        *error = "local_path_empty";
        return false;
    }
    std::ostringstream out;
    for (std::size_t i = 0; i < parts.size(); ++i) {
        if (i) out << '/';
        out << parts[i];
    }
    *normalized = out.str();
    return true;
}

bool replace_json_string(std::string* json, const std::string& key, const std::string& value) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json->find(needle);
    if (pos == std::string::npos) return false;
    pos = json->find(':', pos + needle.size());
    if (pos == std::string::npos) return false;
    const auto quote = json->find('"', pos + 1);
    if (quote == std::string::npos) return false;
    auto end = quote + 1;
    bool escaped = false;
    for (; end < json->size(); ++end) {
        const char c = (*json)[end];
        if (escaped) escaped = false;
        else if (c == '\\') escaped = true;
        else if (c == '"') break;
    }
    if (end >= json->size()) return false;
    json->replace(quote + 1, end - quote - 1, json_escape(value));
    return true;
}

LoopConfig parse_config(const std::string& path, const std::string& json, const std::vector<std::string>& args) {
    LoopConfig config;
    config.config_path = absolute_path(path);
    config.config_dir = dirname_of(config.config_path);
    config.worker_id = extract_json_string(json, av_imgdata::worker::config_key::kWorkerId);
    config.workspace_root = absolute_path(join_path(config.config_dir, extract_json_string(json, av_imgdata::worker::config_key::kWorkspaceRoot)));
    config.path_base_dir = arg_value(args, "--path-base-dir");
    if (config.path_base_dir.empty()) config.path_base_dir = extract_json_string(json, av_imgdata::worker::config_key::kPathBaseDir);
    if (config.path_base_dir.empty()) config.path_base_dir = cwd();
    config.path_base_dir = absolute_path(config.path_base_dir);
    config.poll_interval_seconds = parse_int(extract_json_string(json, av_imgdata::worker::config_key::kPollIntervalSeconds), 2);
    if (config.poll_interval_seconds < 1) config.poll_interval_seconds = 1;
    const std::string auth = extract_object(json, av_imgdata::worker::config_key::kAuth);
    const std::string configured_token = extract_json_string(auth.empty() ? json : auth, av_imgdata::worker::config_key::kTokenFile);
    config.token_file = absolute_path(join_path(config.config_dir, configured_token.empty() ? "../worker.token" : configured_token));
    config.api_url = arg_value(args, "--api-url");
    if (config.api_url.empty()) config.api_url = extract_json_string(json, av_imgdata::worker::config_key::kWorkerApiBaseUrl);
    config.api_url = normalize_url(config.api_url);
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

std::string api_post(const LoopConfig& config, const std::string& action, const std::string& token, const std::string& body) {
    const auto body_path = normalize_path(join_path(config.workspace_root, ".api-" + action + "-request.json"));
    write_file(body_path, body);
    const std::string command =
        "curl -sS -X POST -H " + shell_quote("Content-Type: application/json") +
        " -H " + shell_quote("Authorization: Bearer " + token) +
        " -H " + shell_quote("X-Worker-Id: " + config.worker_id) +
        " --data-binary @" + shell_quote(body_path) + " " + shell_quote(config.api_url + "/" + action) + " 2>&1";
    const auto result = run_command(command);
    return normalized_exit_code(result.exit_code) == 0
        ? result.output
        : "{\"status\":\"error\",\"code\":\"curl_failed\",\"message\":\"" + json_escape(result.output) + "\"}";
}

std::string metadata_json(const LoopConfig& config) {
    return "{\"runtime\":\"cxx-api-loop\",\"protocol_version\":\"" +
        std::string(av_imgdata::worker::kProtocolVersion) +
        "\",\"path_base_dir\":\"" + json_escape(config.path_base_dir) +
        "\",\"input_modes\":" + av_imgdata::worker::input_modes_json() + "}";
}

std::string register_body(const LoopConfig& config) {
    return "{\"worker_id\":\"" + json_escape(config.worker_id) +
        "\",\"version\":\"" + std::string(av_imgdata::worker::kWorkerVersion) +
        "\",\"capabilities\":" + av_imgdata::worker::capabilities_json() +
        ",\"metadata\":" + metadata_json(config) + "}";
}

std::string heartbeat_body(const LoopConfig& config, const std::string& status) {
    return "{\"worker_id\":\"" + json_escape(config.worker_id) +
        "\",\"version\":\"" + std::string(av_imgdata::worker::kWorkerVersion) +
        "\",\"status\":\"" + status +
        "\",\"capabilities\":" + av_imgdata::worker::capabilities_json() +
        ",\"metadata\":" + metadata_json(config) + "}";
}

std::string claim_body(const LoopConfig& config) {
    return "{\"worker_id\":\"" + json_escape(config.worker_id) +
        "\",\"capabilities\":" + av_imgdata::worker::capabilities_json() + "}";
}

LocalJobResult make_local_job(const std::string& claimed, const LoopConfig& config) {
    LocalJobResult result;
    std::string payload = extract_object(claimed, "payload");
    const std::string mode = extract_json_string(payload, "input_mode");
    if (mode != "shared_path") {
        result.code = "unsupported_input_mode";
        result.message = "worker supports input_mode=shared_path only";
        return result;
    }
    std::string relative;
    std::string error;
    if (!safe_relative_path(extract_json_string(payload, "local_path"), &relative, &error)) {
        result.code = error;
        result.message = "invalid shared_path local_path";
        return result;
    }
    result.resolved_path = normalize_path(join_path(config.path_base_dir, relative));
    if (!replace_json_string(&payload, "local_path", result.resolved_path)) {
        result.code = "local_path_missing";
        result.message = "payload local_path could not be replaced";
        return result;
    }
    const std::string job_id = extract_json_string(claimed, "job_id");
    const std::string type = extract_json_string(claimed, "type");
    std::ostringstream job;
    job << "{\"job_id\":\"" << json_escape(job_id) << "\",\"type\":\"" << json_escape(type) << "\"";
    if (payload.size() >= 2) {
        const auto inner = trim(payload.substr(1, payload.size() - 2));
        if (!inner.empty()) job << ',' << inner;
    }
    job << '}';
    result.ok = true;
    result.job_json = job.str();
    return result;
}

std::string worker_command(const LoopConfig& config, const std::string& job_path) {
#ifdef _WIN32
    std::string command = "call " + shell_quote(config.worker_bin);
#else
    std::string command = shell_quote(config.worker_bin);
#endif
    return command + " once --config " + shell_quote(config.config_path) + " --job " + shell_quote(normalize_path(job_path)) + " 2>&1";
}

std::string result_body(const LoopConfig& config, const std::string& id, const std::string& result) {
    return "{\"worker_id\":\"" + json_escape(config.worker_id) +
        "\",\"job_id\":\"" + json_escape(id) +
        "\",\"result\":" + (result.empty() ? "{}" : result) + "}";
}

std::string fail_body(const LoopConfig& config, const std::string& id, const std::string& code, const std::string& message, const std::string& detail = "") {
    std::string out = "{\"worker_id\":\"" + json_escape(config.worker_id) +
        "\",\"job_id\":\"" + json_escape(id) +
        "\",\"error\":{\"code\":\"" + json_escape(code) +
        "\",\"message\":\"" + json_escape(message) + "\"";
    if (!detail.empty() && detail.find('{') != std::string::npos) out += ",\"worker_result\":" + detail;
    return out + "}}";
}

bool worker_success(const CommandResult& result) {
    return normalized_exit_code(result.exit_code) == 0 && result.output.find("\"processor_execution\": \"completed\"") != std::string::npos;
}

bool response_ok(const std::string& response, const std::string& expected_status) {
    return extract_json_string(response, "status") == expected_status;
}

int usage() {
    std::cout << "av-imgdata-worker-api-loop " << av_imgdata::worker::kWorkerVersion
              << "\n\nUsage:\n"
              << "  av-imgdata-worker-api-loop --config <worker-config.json> [--api-url <url>] [--worker-bin <path>] [--path-base-dir <path>] [--max-iterations <n>]\n\n"
              << "The API loop registers explicitly, then sends heartbeats and claims jobs.\n"
              << "shared_path jobs require input_mode=shared_path and a relative local_path.\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
    if (args.empty() || has_arg(args, "--help") || has_arg(args, "-h")) return usage();

    const std::string config_path = arg_value(args, "--config");
    if (config_path.empty()) {
        std::cerr << "ERROR: --config is required\n";
        return 2;
    }
    if (!file_exists(config_path)) {
        std::cerr << "ERROR: config file not found: " << config_path << "\n";
        return 3;
    }

    const LoopConfig config = parse_config(config_path, read_file(config_path), args);
    const int max_iterations = parse_int(arg_value(args, "--max-iterations"), 0);
    if (config.worker_id.empty() || config.api_url.empty() || !file_exists(config.token_file) || !file_exists(config.worker_bin)) {
        std::cerr << "ERROR: incomplete worker configuration\n";
        return 4;
    }

    const std::string token = read_token(config.token_file);
    ensure_dir(join_path(config.workspace_root, "claimed-jobs"));

    const std::string registration = api_post(config, "register", token, register_body(config));
    if (!response_ok(registration, "registered")) {
        std::cerr << "ERROR: worker registration failed: " << registration << "\n";
        return 5;
    }

    int iteration = 0;
    while (max_iterations <= 0 || iteration < max_iterations) {
        ++iteration;
        const std::string heartbeat = api_post(config, "heartbeat", token, heartbeat_body(config, "ready"));
        const std::string claim = api_post(config, "claim", token, claim_body(config));
        const std::string status = extract_json_string(claim, "status");

        std::cout << "{\"mode\":\"api-loop\",\"protocol_version\":\""
                  << av_imgdata::worker::kProtocolVersion
                  << "\",\"iteration\":" << iteration
                  << ",\"worker_id\":\"" << json_escape(config.worker_id)
                  << "\",\"api_url\":\"" << json_escape(config.api_url)
                  << "\",\"path_base_dir\":\"" << json_escape(config.path_base_dir)
                  << "\",\"heartbeat_status\":\"" << json_escape(extract_json_string(heartbeat, "status"))
                  << "\",\"claim_status\":\"" << json_escape(status) << "\"";

        if (status == "claimed") {
            const std::string claimed = extract_object(claim, "job");
            const std::string id = extract_json_string(claimed, "job_id");
            const LocalJobResult local = make_local_job(claimed, config);
            if (!local.ok) {
                api_post(config, "fail", token, fail_body(config, id, local.code, local.message));
                std::cout << ",\"job_id\":\"" << json_escape(id)
                          << "\",\"reported\":\"fail\",\"error_code\":\"" << json_escape(local.code) << "\"";
            } else {
                const std::string job_path = normalize_path(join_path(join_path(config.workspace_root, "claimed-jobs"), id + ".json"));
                write_file(job_path, local.job_json);
                const CommandResult worker_result = run_command(worker_command(config, job_path));
                const int exit_code = normalized_exit_code(worker_result.exit_code);
                if (worker_success(worker_result)) {
                    api_post(config, "result", token, result_body(config, id, worker_result.output));
                    std::cout << ",\"job_id\":\"" << json_escape(id)
                              << "\",\"reported\":\"result\",\"resolved_path\":\"" << json_escape(local.resolved_path)
                              << "\",\"worker_exit_code\":" << exit_code;
                } else {
                    api_post(config, "fail", token, fail_body(config, id, "worker_execution_failed", worker_result.output, worker_result.output));
                    std::cout << ",\"job_id\":\"" << json_escape(id)
                              << "\",\"reported\":\"fail\",\"resolved_path\":\"" << json_escape(local.resolved_path)
                              << "\",\"worker_exit_code\":" << exit_code
                              << ",\"worker_output_preview\":\"" << json_escape(abbreviate(worker_result.output, 600)) << "\"";
                }
            }
        }
        std::cout << "}" << std::endl;
        if (max_iterations > 0 && iteration >= max_iterations) break;
        std::this_thread::sleep_for(std::chrono::seconds(config.poll_interval_seconds));
    }
    return 0;
}
