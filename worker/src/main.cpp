#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#ifndef AV_IMGDATA_WORKER_VERSION
#define AV_IMGDATA_WORKER_VERSION "0.1.0-phase-a"
#endif

namespace {

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
        << "Phase A status:\n"
        << "  Build and packaging skeleton only. DSM Worker API is not implemented yet.\n";
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
    const std::string config = read_file(config_path);
    const bool has_worker_id = config.find("worker_id") != std::string::npos;
    const bool has_processors = config.find("processors") != std::string::npos;
    const bool has_face = config.find("face") != std::string::npos;
    std::cout
        << "{\n"
        << "  \"worker\": {\"name\": \"av-imgdata-worker\", \"version\": \"" << AV_IMGDATA_WORKER_VERSION << "\"},\n"
        << "  \"phase\": \"A\",\n"
        << "  \"config\": {\"path\": \"" << config_path << "\", \"readable\": true},\n"
        << "  \"checks\": {\n"
        << "    \"worker_id_present\": " << (has_worker_id ? "true" : "false") << ",\n"
        << "    \"processors_present\": " << (has_processors ? "true" : "false") << ",\n"
        << "    \"face_processor_config_present\": " << (has_face ? "true" : "false") << "\n"
        << "  },\n"
        << "  \"remote_api\": \"not_implemented\"\n"
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
        << "  \"phase\": \"A\",\n"
        << "  \"mode\": \"once\",\n"
        << "  \"config_path\": \"" << config_path << "\",\n"
        << "  \"job_path\": \"" << job_path << "\",\n"
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
        << "Phase A only verifies build, install and bundle structure.\n";
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
