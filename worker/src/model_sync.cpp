#include "av_imgdata/worker_protocol.h"
#include "av_imgdata/worker_runtime.h"

#include <cctype>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

namespace runtime = av_imgdata::worker::runtime;

struct ManifestFile {
    std::string name;
    std::string sha256;
    bool present = false;
};

std::string lower(std::string value) {
    for (char& c : value) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return value;
}

bool json_bool(const std::string& object, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    auto pos = object.find(needle);
    if (pos == std::string::npos) return false;
    pos = object.find(':', pos + needle.size());
    if (pos == std::string::npos) return false;
    ++pos;
    while (pos < object.size() && std::isspace(static_cast<unsigned char>(object[pos]))) ++pos;
    return object.compare(pos, 4, "true") == 0;
}

std::vector<ManifestFile> parse_manifest_files(const std::string& json) {
    std::vector<ManifestFile> result;
    const auto files_key = json.find("\"files\"");
    if (files_key == std::string::npos) return result;
    const auto array_start = json.find('[', files_key);
    if (array_start == std::string::npos) return result;
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    std::size_t object_start = std::string::npos;
    for (std::size_t i = array_start + 1; i < json.size(); ++i) {
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
        if (c == '{') {
            if (depth == 0) object_start = i;
            ++depth;
        } else if (c == '}') {
            --depth;
            if (depth == 0 && object_start != std::string::npos) {
                const std::string object = json.substr(object_start, i - object_start + 1);
                ManifestFile file;
                file.name = runtime::extract_json_string(object, "name");
                file.sha256 = lower(runtime::extract_json_string(object, "sha256"));
                file.present = json_bool(object, "present");
                if (!file.name.empty()) result.push_back(file);
                object_start = std::string::npos;
            }
        } else if (c == ']' && depth == 0) {
            break;
        }
    }
    return result;
}

std::string normalize_url(std::string value) {
    while (!value.empty() && value.back() == '/') value.pop_back();
    return value;
}

bool safe_filename(const std::string& value) {
    return !value.empty() && value.find('/') == std::string::npos &&
        value.find('\\') == std::string::npos && value.find("..") == std::string::npos;
}

std::string file_sha256(const std::filesystem::path& path) {
#ifdef _WIN32
    const auto result = runtime::run_shell_capture(
        "certutil -hashfile " + runtime::shell_quote(path.string()) + " SHA256 2>NUL"
    );
    if (result.exit_code != 0) return "";
    std::istringstream lines(result.output);
    std::string line;
    while (std::getline(lines, line)) {
        line = runtime::trim(line);
        std::string compact;
        for (char c : line) if (std::isxdigit(static_cast<unsigned char>(c))) compact += c;
        if (compact.size() == 64) return lower(compact);
    }
    return "";
#else
    const auto result = runtime::run_shell_capture(
        "sha256sum " + runtime::shell_quote(path.string()) + " 2>/dev/null"
    );
    if (result.exit_code != 0) return "";
    const auto space = result.output.find_first_of(" \t");
    return lower(result.output.substr(0, space));
#endif
}

bool curl_download(
    const std::string& url,
    const std::string& token,
    const std::string& worker_id,
    const std::filesystem::path& output
) {
    const std::string command =
        "curl -fSsL -H " + runtime::shell_quote("Authorization: Bearer " + token) +
        " -H " + runtime::shell_quote("X-Worker-Id: " + worker_id) +
        " -o " + runtime::shell_quote(output.string()) +
        " " + runtime::shell_quote(url) + " 2>&1";
    const auto result = runtime::run_shell_capture(command);
    if (result.exit_code != 0) {
        std::cerr << "ERROR: download failed for " << url << ": " << result.output << "\n";
        return false;
    }
    return true;
}

int usage() {
    std::cout
        << "av-imgdata-worker-model-sync " << av_imgdata::worker::kWorkerVersion << "\n\n"
        << "Usage:\n"
        << "  av-imgdata-worker-model-sync --api-url <worker-api-url> --token-file <path> --worker-id <id> --model-root <path> [--model-pack buffalo_l]\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
    if (args.empty()) return usage();

    const std::string api_url = normalize_url(runtime::arg_value(args, "--api-url"));
    const std::filesystem::path token_file(runtime::arg_value(args, "--token-file"));
    const std::string worker_id = runtime::arg_value(args, "--worker-id");
    const std::filesystem::path model_root(runtime::arg_value(args, "--model-root"));
    const std::string configured_pack = runtime::arg_value(args, "--model-pack");
    const std::string model_pack = configured_pack.empty() ? "buffalo_l" : configured_pack;
    if (api_url.empty() || token_file.empty() || worker_id.empty() || model_root.empty()) {
        std::cerr << "ERROR: --api-url, --token-file, --worker-id and --model-root are required\n";
        return 2;
    }
    if (!runtime::file_exists(token_file.string())) {
        std::cerr << "ERROR: token file not found: " << token_file << "\n";
        return 3;
    }
    const std::string token = runtime::trim(runtime::read_file(token_file.string()));
    if (token.empty()) {
        std::cerr << "ERROR: token file is empty\n";
        return 4;
    }

    const std::filesystem::path model_dir = runtime::absolute_path(model_root / model_pack);
    if (!runtime::ensure_dir(model_dir.string())) {
        std::cerr << "ERROR: model directory could not be created: " << model_dir << "\n";
        return 5;
    }

    std::error_code error;
    const std::filesystem::path manifest_temp = model_dir / "manifest.json.download";
    const std::string manifest_url = api_url + "/models/" + model_pack + "/manifest";
    if (!curl_download(manifest_url, token, worker_id, manifest_temp)) return 6;
    const std::string manifest = runtime::read_file(manifest_temp.string());
    const auto files = parse_manifest_files(manifest);
    if (files.empty()) {
        std::cerr << "ERROR: manifest contains no model files\n";
        std::filesystem::remove(manifest_temp, error);
        return 7;
    }

    for (const auto& file : files) {
        if (!file.present) continue;
        if (!safe_filename(file.name) || file.sha256.size() != 64) {
            std::cerr << "ERROR: invalid manifest file entry: " << file.name << "\n";
            return 8;
        }
        const std::filesystem::path target = model_dir / file.name;
        if (runtime::file_exists(target.string()) && file_sha256(target) == file.sha256) {
            std::cout << "Model file already current: " << file.name << "\n";
            continue;
        }
        const std::filesystem::path temporary = model_dir / (file.name + ".download");
        std::filesystem::remove(temporary, error);
        const std::string file_url = api_url + "/models/" + model_pack + "/files/" + file.name;
        if (!curl_download(file_url, token, worker_id, temporary)) return 9;
        const std::string actual = file_sha256(temporary);
        if (actual != file.sha256) {
            std::filesystem::remove(temporary, error);
            std::cerr << "ERROR: SHA-256 mismatch for " << file.name
                      << ": expected " << file.sha256 << ", got " << actual << "\n";
            return 10;
        }
        std::filesystem::remove(target, error);
        error.clear();
        std::filesystem::rename(temporary, target, error);
        if (error) {
            std::cerr << "ERROR: model file could not be installed: " << error.message() << "\n";
            return 11;
        }
        std::cout << "Model file synchronized: " << file.name << "\n";
    }

    const std::filesystem::path manifest_target = model_dir / "manifest.json";
    std::filesystem::remove(manifest_target, error);
    error.clear();
    std::filesystem::rename(manifest_temp, manifest_target, error);
    if (error) {
        std::cerr << "ERROR: manifest could not be installed: " << error.message() << "\n";
        return 12;
    }

    std::cout << "{\"status\":\"synchronized\",\"model_pack\":\"" << model_pack
              << "\",\"model_dir\":\"" << runtime::json_escape(model_dir.string()) << "\"}" << std::endl;
    return 0;
}
