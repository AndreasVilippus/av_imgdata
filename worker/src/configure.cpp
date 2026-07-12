#include "av_imgdata/worker_protocol.h"
#include "av_imgdata/worker_runtime.h"

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

namespace runtime = av_imgdata::worker::runtime;

std::string normalize_url(std::string value) {
    while (!value.empty() && value.back() == '/') value.pop_back();
    return value;
}

int usage() {
    std::cout
        << "av-imgdata-worker-configure " << av_imgdata::worker::kWorkerVersion << "\n\n"
        << "Usage:\n"
        << "  av-imgdata-worker-configure --config <path> --worker-id <id> --api-url <worker-api-url> --path-base-dir <path> [--model-pack buffalo_l]\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
    if (args.empty()) return usage();

    const std::string config_path = runtime::arg_value(args, "--config");
    const std::string worker_id = runtime::arg_value(args, "--worker-id");
    const std::string api_url = normalize_url(runtime::arg_value(args, "--api-url"));
    const std::string path_base_dir = runtime::arg_value(args, "--path-base-dir");
    const std::string configured_model_pack = runtime::arg_value(args, "--model-pack");
    const std::string model_pack = configured_model_pack.empty() ? "buffalo_l" : configured_model_pack;
    if (config_path.empty() || worker_id.empty() || api_url.empty() || path_base_dir.empty()) {
        std::cerr << "ERROR: --config, --worker-id, --api-url and --path-base-dir are required\n";
        return 2;
    }

#ifdef _WIN32
    const char* face_processor = "../bin/av-imgdata-face-processor.exe";
    const char* image_processor = "../bin/av-imgdata-image-processor.exe";
#else
    const char* face_processor = "../bin/av-imgdata-face-processor";
    const char* image_processor = "../bin/av-imgdata-image-processor";
#endif

    std::ostringstream config;
    config
        << "{\n"
        << "  \"schema_version\": " << av_imgdata::worker::kConfigSchemaVersion << ",\n"
        << "  \"worker_id\": \"" << runtime::json_escape(worker_id) << "\",\n"
        << "  \"worker_api_base_url\": \"" << runtime::json_escape(api_url) << "\",\n"
        << "  \"auth\": {\"type\": \"worker_token\", \"token_file\": \"../worker.token\"},\n"
        << "  \"workspace_root\": \"../work\",\n"
        << "  \"path_base_dir\": \"" << runtime::json_escape(path_base_dir) << "\",\n"
        << "  \"input_modes\": " << av_imgdata::worker::input_modes_json() << ",\n"
        << "  \"processors\": {\n"
        << "    \"face\": {\"path\": \"" << face_processor
        << "\", \"model_root\": \"../.models/face\", \"model_name\": \"" << runtime::json_escape(model_pack) << "\"},\n"
        << "    \"image_vips\": {\"enabled\": false, \"path\": \"" << image_processor << "\"}\n"
        << "  },\n"
        << "  \"poll_interval_seconds\": 2,\n"
        << "  \"max_parallel_jobs\": 1,\n"
        << "  \"log_level\": \"info\"\n"
        << "}\n";

    if (!runtime::write_file(config_path, config.str())) {
        std::cerr << "ERROR: config file could not be written: " << config_path << "\n";
        return 3;
    }
    std::cout << "{\"status\":\"configured\",\"config_path\":\"" << runtime::json_escape(config_path)
              << "\",\"worker_id\":\"" << runtime::json_escape(worker_id)
              << "\",\"platform\":\""
#ifdef _WIN32
              << "windows"
#else
              << "unix"
#endif
              << "\"}" << std::endl;
    return 0;
}
