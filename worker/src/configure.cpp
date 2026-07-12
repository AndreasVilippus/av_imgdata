#include "av_imgdata/worker_protocol.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

std::string arg_value(const std::vector<std::string>& args, const std::string& name) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i) {
        if (args[i] == name) return args[i + 1];
    }
    return "";
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

    const std::string config_path = arg_value(args, "--config");
    const std::string worker_id = arg_value(args, "--worker-id");
    const std::string api_url = normalize_url(arg_value(args, "--api-url"));
    const std::string path_base_dir = arg_value(args, "--path-base-dir");
    const std::string model_pack = arg_value(args, "--model-pack").empty() ? "buffalo_l" : arg_value(args, "--model-pack");
    if (config_path.empty() || worker_id.empty() || api_url.empty() || path_base_dir.empty()) {
        std::cerr << "ERROR: --config, --worker-id, --api-url and --path-base-dir are required\n";
        return 2;
    }

    const std::filesystem::path output(config_path);
    std::error_code error;
    std::filesystem::create_directories(output.parent_path(), error);
    if (error) {
        std::cerr << "ERROR: config directory could not be created: " << error.message() << "\n";
        return 3;
    }

#ifdef _WIN32
    const char* face_processor = "../bin/av-imgdata-face-processor.exe";
    const char* image_processor = "../bin/av-imgdata-image-processor.exe";
#else
    const char* face_processor = "../bin/av-imgdata-face-processor";
    const char* image_processor = "../bin/av-imgdata-image-processor";
#endif

    std::ofstream out(output, std::ios::binary | std::ios::trunc);
    if (!out) {
        std::cerr << "ERROR: config file could not be opened: " << config_path << "\n";
        return 4;
    }
    out
        << "{\n"
        << "  \"schema_version\": " << av_imgdata::worker::kConfigSchemaVersion << ",\n"
        << "  \"worker_id\": \"" << json_escape(worker_id) << "\",\n"
        << "  \"worker_api_base_url\": \"" << json_escape(api_url) << "\",\n"
        << "  \"auth\": {\"type\": \"worker_token\", \"token_file\": \"../worker.token\"},\n"
        << "  \"workspace_root\": \"../work\",\n"
        << "  \"path_base_dir\": \"" << json_escape(path_base_dir) << "\",\n"
        << "  \"input_modes\": " << av_imgdata::worker::input_modes_json() << ",\n"
        << "  \"processors\": {\n"
        << "    \"face\": {\"path\": \"" << face_processor << "\", \"model_root\": \"../.models/face\", \"model_name\": \"" << json_escape(model_pack) << "\"},\n"
        << "    \"image_vips\": {\"enabled\": false, \"path\": \"" << image_processor << "\"}\n"
        << "  },\n"
        << "  \"poll_interval_seconds\": 2,\n"
        << "  \"max_parallel_jobs\": 1,\n"
        << "  \"log_level\": \"info\"\n"
        << "}\n";
    if (!out) {
        std::cerr << "ERROR: config file could not be written: " << config_path << "\n";
        return 5;
    }
    std::cout << "{\"status\":\"configured\",\"config_path\":\"" << json_escape(config_path)
              << "\",\"worker_id\":\"" << json_escape(worker_id)
              << "\",\"platform\":\""
#ifdef _WIN32
              << "windows"
#else
              << "unix"
#endif
              << "\"}" << std::endl;
    return 0;
}
