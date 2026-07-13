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

struct WorkerConfig {
    std::string config_path;
    std::string config_dir;
    std::string worker_id;
    std::string worker_api_base_url;
    std::string workspace_root;
    std::string face_path;
    std::string face_model_root;
    std::string face_model_name;
    bool image_vips_enabled = true;
    std::string image_vips_path;
    int poll_interval_seconds = 2;
};

struct FaceModelStatus {
    std::string model_dir;
    std::string detector_path;
    std::string recognizer_path;
    std::string manifest_path;
    bool detector_present = false;
    bool recognizer_present = false;
    bool manifest_present = false;
};

struct ReadinessStatus {
    bool has_worker_id = false;
    bool has_processors = false;
    bool has_face = false;
    bool face_binary_exists = false;
    bool models_present = false;
    bool face_version_ok = false;
    bool face_probe_ok = false;
    bool image_vips_configured = false;
    bool image_vips_enabled = true;
    bool image_vips_binary_exists = false;
    bool image_vips_probe_ok = false;
    FaceModelStatus model_status;
    CommandResult face_version;
    CommandResult face_probe;
    CommandResult image_vips_probe;
};

WorkerConfig parse_worker_config(const std::string& config_path, const std::string& config_json) {
    WorkerConfig config;
    config.config_path = runtime::absolute_path(config_path).string();
    config.config_dir = runtime::dirname_of(config.config_path);
    config.worker_id = runtime::extract_json_string(config_json, av_imgdata::worker::config_key::kWorkerId);
    config.worker_api_base_url = runtime::extract_json_string(config_json, av_imgdata::worker::config_key::kWorkerApiBaseUrl);
    config.workspace_root = runtime::extract_json_string(config_json, av_imgdata::worker::config_key::kWorkspaceRoot);
    config.poll_interval_seconds = runtime::parse_int(
        runtime::extract_json_scalar(config_json, av_imgdata::worker::config_key::kPollIntervalSeconds, "2"),
        2
    );
    if (config.poll_interval_seconds < 1) config.poll_interval_seconds = 1;

    const std::string processors = runtime::extract_json_object(config_json, av_imgdata::worker::config_key::kProcessors);
    const std::string face = runtime::extract_json_object(
        processors.empty() ? config_json : processors,
        av_imgdata::worker::config_key::kFace
    );
    config.face_path = runtime::extract_json_string(face.empty() ? config_json : face, "path");
    config.face_model_root = runtime::extract_json_string(face.empty() ? config_json : face, av_imgdata::worker::config_key::kModelRoot);
    config.face_model_name = runtime::extract_json_string(face.empty() ? config_json : face, av_imgdata::worker::config_key::kModelName);
    const std::string image_vips = runtime::extract_json_object(
        processors.empty() ? config_json : processors,
        av_imgdata::worker::config_key::kImageVips
    );
    config.image_vips_path = runtime::extract_json_string(image_vips.empty() ? config_json : image_vips, "path");
    const std::string image_vips_enabled = runtime::extract_json_scalar(image_vips.empty() ? config_json : image_vips, "enabled", "true");
    config.image_vips_enabled = image_vips_enabled != "false" && image_vips_enabled != "0";

    config.face_path = runtime::join_path(config.config_dir, config.face_path);
    config.image_vips_path = runtime::join_path(config.config_dir, config.image_vips_path);
    config.face_model_root = runtime::join_path(config.config_dir, config.face_model_root);
    config.workspace_root = runtime::join_path(config.config_dir, config.workspace_root);
    return config;
}

bool load_config_from_args(const std::vector<std::string>& args, WorkerConfig* config, std::string* config_json) {
    const std::string config_path = runtime::arg_value(args, "--config");
    if (config_path.empty()) {
        std::cerr << "ERROR: --config is required\n";
        return false;
    }
    if (!runtime::file_exists(config_path)) {
        std::cerr << "ERROR: config file not found: " << config_path << "\n";
        return false;
    }
    *config_json = runtime::read_file(config_path);
    *config = parse_worker_config(config_path, *config_json);
    return true;
}

FaceModelStatus inspect_face_models(const WorkerConfig& config) {
    FaceModelStatus status;
    status.model_dir = runtime::join_path(config.face_model_root, config.face_model_name);
    status.detector_path = runtime::join_path(status.model_dir, "det_10g.onnx");
    status.recognizer_path = runtime::join_path(status.model_dir, "w600k_r50.onnx");
    status.manifest_path = runtime::join_path(status.model_dir, "manifest.json");
    status.detector_present = runtime::file_exists(status.detector_path);
    status.recognizer_present = runtime::file_exists(status.recognizer_path);
    status.manifest_present = runtime::file_exists(status.manifest_path);
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
    std::string image_path = runtime::extract_json_string(job_json, "image_path");
    if (image_path.empty()) image_path = runtime::extract_json_string(job_json, "local_path");
    return runtime::join_path(job_dir, image_path);
}

std::string build_processor_payload(
    const std::string& job_json,
    const std::string& job_path,
    const WorkerConfig& config,
    const std::string& type,
    const std::string& command
) {
    std::string job_id = runtime::extract_json_string(job_json, "job_id");
    if (job_id.empty()) job_id = "local";
    const std::string job_dir = runtime::dirname_of(job_path);
    const std::string image_path = resolve_job_image_path(job_json, job_dir);
    const std::string min_confidence = runtime::extract_json_scalar(job_json, "min_confidence", "0.5");
    const std::string max_faces = runtime::extract_json_scalar(job_json, "max_faces", "0");
    const std::string det_size = runtime::extract_json_scalar(job_json, "det_size", "[640,640]");
    const std::string image_paths = runtime::extract_json_array(job_json, "image_paths");

    std::ostringstream payload;
    payload << "{\"contract_version\":\"" << av_imgdata::worker::kProtocolVersion << "\",";
    payload << "\"job_id\":\"" << runtime::json_escape(job_id) << "\",";
    payload << "\"type\":\"" << runtime::json_escape(type) << "\",";
    if (command == "detect_batch" || command == "embed_batch") {
        payload << "\"image_paths\":" << (image_paths.empty() ? "[]" : image_paths) << ',';
    } else {
        payload << "\"image_path\":\"" << runtime::json_escape(image_path) << "\",";
        payload << "\"input\":{\"image_path\":\"" << runtime::json_escape(image_path)
                << "\",\"source_id\":\"" << runtime::json_escape(image_path) << "\"},";
    }
    payload << "\"model_root\":\"" << runtime::json_escape(config.face_model_root) << "\",";
    payload << "\"model_name\":\"" << runtime::json_escape(config.face_model_name) << "\",";
    payload << "\"min_confidence\":" << min_confidence << ',';
    payload << "\"max_faces\":" << max_faces << ',';
    payload << "\"det_size\":" << det_size << ',';
    payload << "\"options\":{";
    payload << "\"model_root\":\"" << runtime::json_escape(config.face_model_root) << "\",";
    payload << "\"model_name\":\"" << runtime::json_escape(config.face_model_name) << "\",";
    payload << "\"min_confidence\":" << min_confidence << ',';
    payload << "\"max_faces\":" << max_faces << ',';
    payload << "\"det_size\":" << det_size << ',';
    payload << "\"normalize_coordinates\":true}}";
    return payload.str();
}

ReadinessStatus check_readiness(const WorkerConfig& config, const std::string& config_json) {
    ReadinessStatus status;
    status.model_status = inspect_face_models(config);
    status.models_present = face_models_present(status.model_status);
    status.has_worker_id = !config.worker_id.empty();
    status.has_processors = !runtime::extract_json_object(config_json, av_imgdata::worker::config_key::kProcessors).empty();
    status.has_face = !config.face_path.empty();
    status.face_binary_exists = runtime::file_exists(config.face_path);
    status.image_vips_configured = !config.image_vips_path.empty();
    status.image_vips_enabled = config.image_vips_enabled;
    status.image_vips_binary_exists = status.image_vips_configured && runtime::file_exists(config.image_vips_path);
    if (status.image_vips_enabled && status.image_vips_binary_exists) {
        status.image_vips_probe = runtime::run_process_capture(config.image_vips_path, {"probe"});
        status.image_vips_probe_ok = status.image_vips_probe.exit_code == 0;
    }
    if (status.face_binary_exists) {
        status.face_version = runtime::run_process_capture(config.face_path, {"version"});
        status.face_version_ok = status.face_version.exit_code == 0;
        if (status.models_present) {
            status.face_probe = runtime::run_process_capture(
                config.face_path,
                {"probe", "--model-root", config.face_model_root, "--model-name", config.face_model_name}
            );
            status.face_probe_ok = status.face_probe.exit_code == 0;
        } else {
            status.face_probe.exit_code = 5;
            status.face_probe.output = missing_model_message(status.model_status);
        }
    }
    return status;
}

bool ready_for_face_jobs(const ReadinessStatus& status) {
    return status.has_worker_id && status.has_processors && status.has_face &&
        status.face_binary_exists && status.models_present && status.face_version_ok && status.face_probe_ok;
}

int print_usage() {
    std::cout
        << "av-imgdata-worker " << av_imgdata::worker::kWorkerVersion << "\n\n"
        << "Usage:\n"
        << "  av-imgdata-worker version\n"
        << "  av-imgdata-worker probe --config <worker-config.json>\n"
        << "  av-imgdata-worker once --config <worker-config.json> --job <job.json>\n"
        << "  av-imgdata-worker run --config <worker-config.json> [--max-iterations <n>]\n";
    return 0;
}

int command_version() {
    std::cout << "av-imgdata-worker " << av_imgdata::worker::kWorkerVersion << "\n";
    return 0;
}

int command_probe(const std::vector<std::string>& args) {
    WorkerConfig config;
    std::string config_json;
    if (!load_config_from_args(args, &config, &config_json)) return 2;
    const ReadinessStatus status = check_readiness(config, config_json);
    const bool ready = ready_for_face_jobs(status);

    std::cout
        << "{\n"
        << "  \"schema_version\": 1,\n"
        << "  \"component\": \"external_worker\",\n"
        << "  \"phase\": \"" << (ready ? "ready" : "blocked") << "\",\n"
        << "  \"worker\": {\"name\": \"av-imgdata-worker\", \"version\": \"" << av_imgdata::worker::kWorkerVersion
        << "\", \"protocol_version\": \"" << av_imgdata::worker::kProtocolVersion << "\"},\n"
        << "  \"config\": {\n"
        << "    \"path\": \"" << runtime::json_escape(config.config_path) << "\",\n"
        << "    \"readable\": true,\n"
        << "    \"worker_id\": \"" << runtime::json_escape(config.worker_id) << "\",\n"
        << "    \"worker_api_base_url\": \"" << runtime::json_escape(config.worker_api_base_url) << "\",\n"
        << "    \"workspace_root\": \"" << runtime::json_escape(config.workspace_root) << "\",\n"
        << "    \"poll_interval_seconds\": " << config.poll_interval_seconds << "\n"
        << "  },\n"
        << "  \"checks\": {\n"
        << "    \"worker_id_present\": " << (status.has_worker_id ? "true" : "false") << ",\n"
        << "    \"processors_present\": " << (status.has_processors ? "true" : "false") << ",\n"
        << "    \"face_processor_config_present\": " << (status.has_face ? "true" : "false") << ",\n"
        << "    \"face_processor_binary_exists\": " << (status.face_binary_exists ? "true" : "false") << ",\n"
        << "    \"face_models_present\": " << (status.models_present ? "true" : "false") << ",\n"
        << "    \"face_model_manifest_present\": " << (status.model_status.manifest_present ? "true" : "false") << ",\n"
        << "    \"image_vips_configured\": " << (status.image_vips_configured ? "true" : "false") << ",\n"
        << "    \"image_vips_enabled\": " << (status.image_vips_enabled ? "true" : "false") << ",\n"
        << "    \"image_vips_binary_exists\": " << (status.image_vips_binary_exists ? "true" : "false") << ",\n"
        << "    \"image_vips_probe_ok\": " << (status.image_vips_probe_ok ? "true" : "false") << "\n"
        << "  },\n"
        << "  \"processors\": [{\n"
        << "    \"name\": \"av-imgdata-face-processor\",\n"
        << "    \"path\": \"" << runtime::json_escape(config.face_path) << "\",\n"
        << "    \"model_root\": \"" << runtime::json_escape(config.face_model_root) << "\",\n"
        << "    \"model_name\": \"" << runtime::json_escape(config.face_model_name) << "\",\n"
        << "    \"binary_exists\": " << (status.face_binary_exists ? "true" : "false") << ",\n"
        << "    \"version_ok\": " << (status.face_version_ok ? "true" : "false") << ",\n"
        << "    \"version_output\": \"" << runtime::json_escape(status.face_version.output) << "\",\n"
        << R"(    "models": {
      "managed_by": "dsm",
      "distributed_with_worker": false,
      "license_authority": "dsm",
)"
        << "      \"model_dir\": \"" << runtime::json_escape(status.model_status.model_dir) << "\",\n"
        << "      \"detector_path\": \"" << runtime::json_escape(status.model_status.detector_path) << "\",\n"
        << "      \"recognizer_path\": \"" << runtime::json_escape(status.model_status.recognizer_path) << "\",\n"
        << "      \"manifest_path\": \"" << runtime::json_escape(status.model_status.manifest_path) << "\",\n"
        << "      \"detector_present\": " << (status.model_status.detector_present ? "true" : "false") << ",\n"
        << "      \"recognizer_present\": " << (status.model_status.recognizer_present ? "true" : "false") << ",\n"
        << "      \"models_present\": " << (status.models_present ? "true" : "false") << ",\n"
        << "      \"manifest_present\": " << (status.model_status.manifest_present ? "true" : "false") << "\n"
        << "    },\n"
        << "    \"probe_ok\": " << (status.face_probe_ok ? "true" : "false") << ",\n"
        << "    \"probe_output\": \"" << runtime::json_escape(status.face_probe.output) << "\"\n"
        << "  },{\n"
        << "    \"name\": \"av-imgdata-image-processor\",\n"
        << "    \"backend\": \"libvips\",\n"
        << "    \"enabled\": " << (status.image_vips_enabled ? "true" : "false") << ",\n"
        << "    \"path\": \"" << runtime::json_escape(config.image_vips_path) << "\",\n"
        << "    \"binary_exists\": " << (status.image_vips_binary_exists ? "true" : "false") << ",\n"
        << "    \"probe_ok\": " << (status.image_vips_probe_ok ? "true" : "false") << ",\n"
        << "    \"probe_output\": \"" << runtime::json_escape(status.image_vips_probe.output) << "\"\n"
        << "  }],\n"
        << "  \"capabilities\": " << (ready ? av_imgdata::worker::capabilities_json() : "[]") << ",\n"
        << "  \"input_modes\": " << av_imgdata::worker::input_modes_json() << ",\n"
        << "  \"remote_api\": {\"status\": \"available_via_api_loop\", \"run_loop_ready\": true}\n"
        << "}\n";
    return status.has_worker_id && status.has_processors && status.has_face ? 0 : 4;
}

int command_once(const std::vector<std::string>& args) {
    const std::string config_path = runtime::arg_value(args, "--config");
    const std::string job_path = runtime::arg_value(args, "--job");
    if (config_path.empty() || job_path.empty()) {
        std::cerr << "ERROR: --config and --job are required\n";
        return 2;
    }
    if (!runtime::file_exists(config_path) || !runtime::file_exists(job_path)) {
        std::cerr << "ERROR: config or job file not found\n";
        return 3;
    }

    const WorkerConfig config = parse_worker_config(config_path, runtime::read_file(config_path));
    const std::string job = runtime::read_file(job_path);
    std::string job_id = runtime::extract_json_string(job, "job_id");
    if (job_id.empty()) job_id = "local";
    const std::string type = runtime::extract_json_string(job, "type");
    const std::string processor_command = face_command_from_type(type);
    const bool has_job_id = job.find("job_id") != std::string::npos;
    const bool has_type = !type.empty();
    const bool face_binary_exists = runtime::file_exists(config.face_path);
    const FaceModelStatus model_status = inspect_face_models(config);
    const bool models_present = face_models_present(model_status);
    const std::string job_dir = runtime::dirname_of(job_path);
    const std::string safe_job_name = runtime::basename_of(job_path);
    const std::string processor_input = runtime::join_path(job_dir, safe_job_name + ".processor-input.json");
    const std::string processor_output = runtime::join_path(job_dir, safe_job_name + ".processor-result.json");

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
        if (!runtime::write_file(processor_input, payload)) {
            processor_execution = "failed";
            error_code = "input_write_failed";
            error_message = processor_input;
        } else {
            processor_result = runtime::run_process_capture(
                config.face_path,
                {processor_command, "--input", processor_input, "--output", processor_output}
            );
            processor_output_json = runtime::read_file(processor_output);
            processor_execution = processor_result.exit_code == 0 ? "completed" : "failed";
            if (processor_result.exit_code != 0) {
                error_code = "processor_failed";
                error_message = processor_result.output;
            }
        }
    }

    std::cout
        << "{\n"
        << "  \"schema_version\": 1,\n"
        << "  \"component\": \"external_worker\",\n"
        << "  \"worker\": {\"name\": \"av-imgdata-worker\", \"version\": \"" << av_imgdata::worker::kWorkerVersion << "\"},\n"
        << "  \"phase\": \"" << (processor_execution == "completed" ? "finished" : processor_execution == "blocked" ? "blocked" : "failed") << "\",\n"
        << "  \"mode\": \"once\",\n"
        << "  \"config_path\": \"" << runtime::json_escape(config_path) << "\",\n"
        << "  \"job_path\": \"" << runtime::json_escape(job_path) << "\",\n"
        << "  \"checks\": {\"job_id_present\": " << (has_job_id ? "true" : "false")
        << ", \"type_present\": " << (has_type ? "true" : "false")
        << ", \"face_processor_binary_exists\": " << (face_binary_exists ? "true" : "false")
        << ", \"face_models_present\": " << (models_present ? "true" : "false") << "},\n"
        << "  \"job\": {\"job_id\": \"" << runtime::json_escape(job_id)
        << "\", \"type\": \"" << runtime::json_escape(type)
        << "\", \"processor_command\": \"" << runtime::json_escape(processor_command) << "\"},\n"
        << "  \"processor_execution\": \"" << runtime::json_escape(processor_execution) << "\",\n"
        << "  \"processor\": {\"path\": \"" << runtime::json_escape(config.face_path)
        << "\", \"exit_code\": " << processor_result.exit_code
        << ", \"output\": \"" << runtime::json_escape(processor_result.output) << "\"},\n"
        << "  \"artifacts\": {\"processor_input\": \"" << runtime::json_escape(processor_input)
        << "\", \"processor_result\": \"" << runtime::json_escape(processor_output) << "\"}";
    if (!processor_output_json.empty() && processor_output_json.find('{') != std::string::npos) {
        std::cout << ",\n  \"processor_result\": " << processor_output_json;
    }
    if (!error_code.empty()) {
        std::cout << ",\n  \"error\": {\"code\": \"" << runtime::json_escape(error_code)
                  << "\", \"message\": \"" << runtime::json_escape(error_message) << "\"}";
    }
    std::cout << "\n}\n";
    return processor_execution == "completed" ? 0 : 4;
}

int command_run(const std::vector<std::string>& args) {
    WorkerConfig config;
    std::string config_json;
    if (!load_config_from_args(args, &config, &config_json)) return 2;
    const int max_iterations = runtime::parse_int(runtime::arg_value(args, "--max-iterations"), 0);
    int iteration = 0;
    while (max_iterations <= 0 || iteration < max_iterations) {
        ++iteration;
        const ReadinessStatus status = check_readiness(config, config_json);
        const bool ready = ready_for_face_jobs(status);
        std::cout
            << "{\"schema_version\":1,\"component\":\"external_worker\""
            << ",\"phase\":\"" << (ready ? "ready" : "blocked") << "\""
            << ",\"worker\":{\"name\":\"av-imgdata-worker\",\"version\":\"" << av_imgdata::worker::kWorkerVersion << "\"}"
            << ",\"mode\":\"run\""
            << ",\"iteration\":" << iteration
            << ",\"worker_id\":\"" << runtime::json_escape(config.worker_id) << "\""
            << ",\"ready\":" << (ready ? "true" : "false")
            << ",\"worker_api_base_url\":\"" << runtime::json_escape(config.worker_api_base_url) << "\""
            << ",\"poll_interval_seconds\":" << config.poll_interval_seconds
            << ",\"checks\":{\"face_processor_binary_exists\":" << (status.face_binary_exists ? "true" : "false")
            << ",\"face_models_present\":" << (status.models_present ? "true" : "false")
            << ",\"face_probe_ok\":" << (status.face_probe_ok ? "true" : "false")
            << "}}" << std::endl;
        if (max_iterations > 0 && iteration >= max_iterations) break;
        std::this_thread::sleep_for(std::chrono::seconds(config.poll_interval_seconds));
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
    if (args.empty() || runtime::has_arg(args, "--help") || runtime::has_arg(args, "-h")) return print_usage();
    const std::string command = args[0];
    if (command == "version") return command_version();
    if (command == "probe") return command_probe(args);
    if (command == "once") return command_once(args);
    if (command == "run") return command_run(args);
    std::cerr << "ERROR: unknown command: " << command << "\n";
    print_usage();
    return 2;
}
