#include "av_imgdata/worker_protocol.h"
#include "av_imgdata/worker_runtime.h"

#include <chrono>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {

namespace runtime = av_imgdata::worker::runtime;
using runtime::CommandResult;

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

std::string normalize_url(std::string url) {
    while (!url.empty() && url.back() == '/') url.pop_back();
    return url;
}

std::string read_token(const std::string& path) {
    return runtime::trim(runtime::read_file(path));
}

LoopConfig parse_config(const std::string& path, const std::string& json, const std::vector<std::string>& args) {
    LoopConfig config;
    config.config_path = runtime::absolute_path(path).string();
    config.config_dir = runtime::dirname_of(config.config_path);
    config.worker_id = runtime::extract_json_string(json, av_imgdata::worker::config_key::kWorkerId);
    config.workspace_root = runtime::join_path(
        config.config_dir,
        runtime::extract_json_string(json, av_imgdata::worker::config_key::kWorkspaceRoot)
    );
    config.path_base_dir = runtime::arg_value(args, "--path-base-dir");
    if (config.path_base_dir.empty()) {
        config.path_base_dir = runtime::extract_json_string(json, av_imgdata::worker::config_key::kPathBaseDir);
    }
    if (config.path_base_dir.empty()) config.path_base_dir = std::filesystem::current_path().string();
    config.path_base_dir = runtime::absolute_path(config.path_base_dir).string();
    config.poll_interval_seconds = runtime::parse_int(
        runtime::extract_json_scalar(json, av_imgdata::worker::config_key::kPollIntervalSeconds, "2"),
        2
    );
    if (config.poll_interval_seconds < 1) config.poll_interval_seconds = 1;

    const std::string auth = runtime::extract_json_object(json, av_imgdata::worker::config_key::kAuth);
    const std::string configured_token = runtime::extract_json_string(
        auth.empty() ? json : auth,
        av_imgdata::worker::config_key::kTokenFile
    );
    config.token_file = runtime::join_path(
        config.config_dir,
        configured_token.empty() ? "../worker.token" : configured_token
    );
    config.api_url = runtime::arg_value(args, "--api-url");
    if (config.api_url.empty()) {
        config.api_url = runtime::extract_json_string(json, av_imgdata::worker::config_key::kWorkerApiBaseUrl);
    }
    config.api_url = normalize_url(config.api_url);
    config.worker_bin = runtime::arg_value(args, "--worker-bin");
    if (config.worker_bin.empty()) {
#ifdef _WIN32
        config.worker_bin = runtime::join_path(config.config_dir, "../bin/av-imgdata-worker.exe");
#else
        config.worker_bin = runtime::join_path(config.config_dir, "../bin/av-imgdata-worker");
#endif
    }
    config.worker_bin = runtime::absolute_path(config.worker_bin).string();
    return config;
}

std::string api_post(const LoopConfig& config, const std::string& action, const std::string& token, const std::string& body) {
    const std::string body_path = runtime::join_path(config.workspace_root, ".api-" + action + "-request.json");
    runtime::write_file(body_path, body);
    const std::string command =
        "curl -fSsL -X POST -H " + runtime::shell_quote("Content-Type: application/json") +
        " -H " + runtime::shell_quote("Authorization: Bearer " + token) +
        " -H " + runtime::shell_quote("X-Worker-Id: " + config.worker_id) +
        " --data-binary @" + runtime::shell_quote(body_path) +
        " " + runtime::shell_quote(config.api_url + "/" + action) + " 2>&1";
    const CommandResult result = runtime::run_shell_capture(command);
    return result.exit_code == 0
        ? result.output
        : "{\"status\":\"error\",\"code\":\"curl_failed\",\"message\":\"" + runtime::json_escape(result.output) + "\"}";
}

std::string metadata_json(const LoopConfig& config) {
    return "{\"runtime\":\"cxx-api-loop\",\"protocol_version\":\"" +
        std::string(av_imgdata::worker::kProtocolVersion) +
        "\",\"path_base_dir\":\"" + runtime::json_escape(config.path_base_dir) +
        "\",\"input_modes\":" + av_imgdata::worker::input_modes_json() + "}";
}

std::string register_body(const LoopConfig& config) {
    return "{\"worker_id\":\"" + runtime::json_escape(config.worker_id) +
        "\",\"version\":\"" + std::string(av_imgdata::worker::kWorkerVersion) +
        "\",\"capabilities\":" + av_imgdata::worker::capabilities_json() +
        ",\"metadata\":" + metadata_json(config) + "}";
}

std::string heartbeat_body(const LoopConfig& config, const std::string& status) {
    return "{\"worker_id\":\"" + runtime::json_escape(config.worker_id) +
        "\",\"version\":\"" + std::string(av_imgdata::worker::kWorkerVersion) +
        "\",\"status\":\"" + runtime::json_escape(status) +
        "\",\"capabilities\":" + av_imgdata::worker::capabilities_json() +
        ",\"metadata\":" + metadata_json(config) + "}";
}

std::string claim_body(const LoopConfig& config) {
    return "{\"worker_id\":\"" + runtime::json_escape(config.worker_id) +
        "\",\"capabilities\":" + av_imgdata::worker::capabilities_json() + "}";
}

LocalJobResult make_local_job(const std::string& claimed, const LoopConfig& config) {
    LocalJobResult result;
    std::string payload = runtime::extract_json_object(claimed, "payload");
    const std::string mode = runtime::extract_json_string(payload, "input_mode");
    if (mode != "shared_path") {
        result.code = "unsupported_input_mode";
        result.message = "worker supports input_mode=shared_path only";
        return result;
    }
    std::string relative;
    std::string error;
    if (!runtime::safe_relative_path(runtime::extract_json_string(payload, "local_path"), &relative, &error)) {
        result.code = error;
        result.message = "invalid shared_path local_path";
        return result;
    }
    result.resolved_path = runtime::join_path(config.path_base_dir, relative);
    if (!runtime::replace_json_string(&payload, "local_path", result.resolved_path)) {
        result.code = "local_path_missing";
        result.message = "payload local_path could not be replaced";
        return result;
    }
    const std::string job_id = runtime::extract_json_string(claimed, "job_id");
    const std::string type = runtime::extract_json_string(claimed, "type");
    std::ostringstream job;
    job << "{\"job_id\":\"" << runtime::json_escape(job_id)
        << "\",\"type\":\"" << runtime::json_escape(type) << "\"";
    if (payload.size() >= 2) {
        const std::string inner = runtime::trim(payload.substr(1, payload.size() - 2));
        if (!inner.empty()) job << ',' << inner;
    }
    job << '}';
    result.ok = true;
    result.job_json = job.str();
    return result;
}

std::string worker_command(const LoopConfig& config, const std::string& job_path) {
    return runtime::shell_quote(config.worker_bin) +
        " once --config " + runtime::shell_quote(config.config_path) +
        " --job " + runtime::shell_quote(job_path) + " 2>&1";
}

std::string result_body(const LoopConfig& config, const std::string& id, const std::string& result) {
    return "{\"worker_id\":\"" + runtime::json_escape(config.worker_id) +
        "\",\"job_id\":\"" + runtime::json_escape(id) +
        "\",\"result\":" + (result.empty() ? "{}" : result) + "}";
}

std::string fail_body(
    const LoopConfig& config,
    const std::string& id,
    const std::string& code,
    const std::string& message,
    const std::string& detail = ""
) {
    std::string output = "{\"worker_id\":\"" + runtime::json_escape(config.worker_id) +
        "\",\"job_id\":\"" + runtime::json_escape(id) +
        "\",\"error\":{\"code\":\"" + runtime::json_escape(code) +
        "\",\"message\":\"" + runtime::json_escape(message) + "\"";
    if (!detail.empty() && detail.find('{') != std::string::npos) output += ",\"worker_result\":" + detail;
    return output + "}}";
}

bool worker_success(const CommandResult& result) {
    return result.exit_code == 0 && result.output.find("\"processor_execution\": \"completed\"") != std::string::npos;
}

bool response_ok(const std::string& response, const std::string& expected_status) {
    return runtime::extract_json_string(response, "status") == expected_status;
}

int usage() {
    std::cout
        << "av-imgdata-worker-api-loop " << av_imgdata::worker::kWorkerVersion << "\n\n"
        << "Usage:\n"
        << "  av-imgdata-worker-api-loop --config <worker-config.json> [--api-url <url>] [--worker-bin <path>] [--path-base-dir <path>] [--max-iterations <n>]\n\n"
        << "The API loop registers explicitly, then sends heartbeats and claims jobs.\n"
        << "shared_path jobs require input_mode=shared_path and a relative local_path.\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
    if (args.empty() || runtime::has_arg(args, "--help") || runtime::has_arg(args, "-h")) return usage();

    const std::string config_path = runtime::arg_value(args, "--config");
    if (config_path.empty()) {
        std::cerr << "ERROR: --config is required\n";
        return 2;
    }
    if (!runtime::file_exists(config_path)) {
        std::cerr << "ERROR: config file not found: " << config_path << "\n";
        return 3;
    }

    const LoopConfig config = parse_config(config_path, runtime::read_file(config_path), args);
    const int max_iterations = runtime::parse_int(runtime::arg_value(args, "--max-iterations"), 0);
    if (config.worker_id.empty() || config.api_url.empty() ||
        !runtime::file_exists(config.token_file) || !runtime::file_exists(config.worker_bin)) {
        std::cerr << "ERROR: incomplete worker configuration\n";
        return 4;
    }

    const std::string token = read_token(config.token_file);
    runtime::ensure_dir(runtime::join_path(config.workspace_root, "claimed-jobs"));

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
        const std::string status = runtime::extract_json_string(claim, "status");

        std::cout
            << "{\"schema_version\":1,\"component\":\"external_worker\",\"phase\":\"running\""
            << ",\"mode\":\"api-loop\",\"protocol_version\":\"" << av_imgdata::worker::kProtocolVersion << "\""
            << ",\"iteration\":" << iteration
            << ",\"worker_id\":\"" << runtime::json_escape(config.worker_id) << "\""
            << ",\"api_url\":\"" << runtime::json_escape(config.api_url) << "\""
            << ",\"path_base_dir\":\"" << runtime::json_escape(config.path_base_dir) << "\""
            << ",\"heartbeat_status\":\"" << runtime::json_escape(runtime::extract_json_string(heartbeat, "status")) << "\""
            << ",\"claim_status\":\"" << runtime::json_escape(status) << "\"";

        if (status == "claimed") {
            const std::string claimed = runtime::extract_json_object(claim, "job");
            const std::string id = runtime::extract_json_string(claimed, "job_id");
            const LocalJobResult local = make_local_job(claimed, config);
            if (!local.ok) {
                api_post(config, "fail", token, fail_body(config, id, local.code, local.message));
                std::cout << ",\"job_id\":\"" << runtime::json_escape(id)
                          << "\",\"reported\":\"fail\",\"error_code\":\"" << runtime::json_escape(local.code) << "\"";
            } else {
                const std::string job_path = runtime::join_path(
                    runtime::join_path(config.workspace_root, "claimed-jobs"),
                    id + ".json"
                );
                runtime::write_file(job_path, local.job_json);
                const CommandResult worker_result = runtime::run_shell_capture(worker_command(config, job_path));
                if (worker_success(worker_result)) {
                    api_post(config, "result", token, result_body(config, id, worker_result.output));
                    std::cout << ",\"job_id\":\"" << runtime::json_escape(id)
                              << "\",\"reported\":\"result\",\"resolved_path\":\"" << runtime::json_escape(local.resolved_path)
                              << "\",\"worker_exit_code\":" << worker_result.exit_code;
                } else {
                    api_post(config, "fail", token, fail_body(config, id, "worker_execution_failed", worker_result.output, worker_result.output));
                    std::cout << ",\"job_id\":\"" << runtime::json_escape(id)
                              << "\",\"reported\":\"fail\",\"resolved_path\":\"" << runtime::json_escape(local.resolved_path)
                              << "\",\"worker_exit_code\":" << worker_result.exit_code
                              << ",\"worker_output_preview\":\"" << runtime::json_escape(runtime::abbreviate(worker_result.output, 600)) << "\"";
                }
            }
        }
        std::cout << "}" << std::endl;
        if (max_iterations > 0 && iteration >= max_iterations) break;
        std::this_thread::sleep_for(std::chrono::seconds(config.poll_interval_seconds));
    }
    return 0;
}
