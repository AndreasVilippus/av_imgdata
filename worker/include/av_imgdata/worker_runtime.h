#pragma once

#include <array>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#ifdef _WIN32
#define AV_IMGDATA_POPEN _popen
#define AV_IMGDATA_PCLOSE _pclose
#else
#define AV_IMGDATA_POPEN popen
#define AV_IMGDATA_PCLOSE pclose
#endif

namespace av_imgdata::worker::runtime {

struct CommandResult {
    int exit_code = -1;
    std::string output;
    std::string command;
};

inline std::string arg_value(const std::vector<std::string>& args, const std::string& name) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i) {
        if (args[i] == name) return args[i + 1];
    }
    return "";
}

inline bool has_arg(const std::vector<std::string>& args, const std::string& name) {
    for (const auto& item : args) if (item == name) return true;
    return false;
}

inline int parse_int(const std::string& value, int fallback) {
    if (value.empty()) return fallback;
    char* end = nullptr;
    const long parsed = std::strtol(value.c_str(), &end, 10);
    return end == value.c_str() ? fallback : static_cast<int>(parsed);
}

inline int normalized_exit_code(int raw) {
#ifndef _WIN32
    if (raw >= 256 && raw % 256 == 0) return raw / 256;
#endif
    return raw;
}

inline std::filesystem::path absolute_path(const std::filesystem::path& path) {
    std::error_code error;
    const auto resolved = std::filesystem::absolute(path, error).lexically_normal();
    return error ? path.lexically_normal() : resolved;
}

inline std::filesystem::path resolve_relative(const std::filesystem::path& base, const std::filesystem::path& value) {
    if (value.empty()) return value;
    return absolute_path(value.is_absolute() ? value : base / value);
}

inline std::string dirname_of(const std::string& path) {
    const auto parent = std::filesystem::path(path).parent_path();
    return parent.empty() ? "." : parent.string();
}

inline std::string basename_of(const std::string& path) {
    return std::filesystem::path(path).filename().string();
}

inline std::string join_path(const std::string& base, const std::string& value) {
    if (value.empty()) return value;
    return resolve_relative(std::filesystem::path(base), std::filesystem::path(value)).string();
}

inline bool file_exists(const std::string& path) {
    std::error_code error;
    return !path.empty() && std::filesystem::is_regular_file(std::filesystem::path(path), error);
}

inline bool ensure_dir(const std::string& path) {
    if (path.empty()) return false;
    std::error_code error;
    std::filesystem::create_directories(std::filesystem::path(path), error);
    return !error;
}

inline std::string read_file(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

inline bool write_file(const std::string& path, const std::string& text) {
    const auto target = std::filesystem::path(path);
    if (!target.parent_path().empty()) ensure_dir(target.parent_path().string());
    std::ofstream output(target, std::ios::binary | std::ios::trunc);
    if (!output) return false;
    output << text;
    return static_cast<bool>(output);
}

inline std::string trim(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) value.pop_back();
    std::size_t first = 0;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first]))) ++first;
    return value.substr(first);
}

inline std::string abbreviate(const std::string& value, std::size_t limit) {
    if (value.size() <= limit) return value;
    return value.substr(0, limit > 3 ? limit - 3 : limit) + (limit > 3 ? "..." : "");
}

inline std::string json_escape(const std::string& value) {
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

inline std::string shell_quote(const std::string& value) {
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

inline CommandResult run_shell_capture(const std::string& command) {
    CommandResult result;
    result.command = command;
    std::array<char, 512> buffer{};
    FILE* pipe = AV_IMGDATA_POPEN(command.c_str(), "r");
    if (!pipe) {
        result.output = "popen_failed";
        return result;
    }
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe)) result.output += buffer.data();
    result.exit_code = normalized_exit_code(AV_IMGDATA_PCLOSE(pipe));
    result.output = trim(result.output);
    return result;
}

inline std::string build_process_command(const std::string& executable, const std::vector<std::string>& arguments) {
#ifdef _WIN32
    // cmd.exe requires an additional outer quote pair when the command begins
    // with a quoted executable path. Without it, paths containing spaces are
    // parsed as a command name including the first argument.
    std::string command = "cmd.exe /D /S /C \"\"" + executable + "\"";
    for (const auto& argument : arguments) command += " " + shell_quote(argument);
    command += " 2>&1\"";
    return command;
#else
    std::string command = shell_quote(executable);
    for (const auto& argument : arguments) command += " " + shell_quote(argument);
    command += " 2>&1";
    return command;
#endif
}

inline CommandResult run_process_capture(const std::string& executable, const std::vector<std::string>& arguments) {
    return run_shell_capture(build_process_command(executable, arguments));
}

inline std::string extract_json_string(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return "";
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return "";
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
                default: value += c;
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

inline std::string extract_block(const std::string& json, const std::string& key, char open, char close) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find(open, pos + needle.size());
    if (pos == std::string::npos) return "";
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
        if (in_string) continue;
        if (c == open) ++depth;
        else if (c == close && --depth == 0) return json.substr(pos, i - pos + 1);
    }
    return "";
}

inline std::string extract_json_object(const std::string& json, const std::string& key) {
    return extract_block(json, key, '{', '}');
}

inline std::string extract_json_array(const std::string& json, const std::string& key) {
    return extract_block(json, key, '[', ']');
}

inline std::string extract_json_scalar(const std::string& json, const std::string& key, const std::string& fallback) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return fallback;
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return fallback;
    ++pos;
    while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) ++pos;
    if (pos >= json.size()) return fallback;
    if (json[pos] == '[') {
        const auto array = extract_json_array(json, key);
        return array.empty() ? fallback : array;
    }
    std::size_t end = pos;
    while (end < json.size() && json[end] != ',' && json[end] != '}' && json[end] != ']') ++end;
    const auto value = trim(json.substr(pos, end - pos));
    return value.empty() ? fallback : value;
}

inline bool replace_json_string(std::string* json, const std::string& key, const std::string& value) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json->find(needle);
    if (pos == std::string::npos) return false;
    pos = json->find(':', pos + needle.size());
    if (pos == std::string::npos) return false;
    auto quote = json->find('"', pos + 1);
    if (quote == std::string::npos) return false;
    auto end = quote + 1;
    bool escaping = false;
    for (; end < json->size(); ++end) {
        const char c = (*json)[end];
        if (escaping) escaping = false;
        else if (c == '\\') escaping = true;
        else if (c == '"') break;
    }
    if (end >= json->size()) return false;
    json->replace(quote + 1, end - quote - 1, json_escape(value));
    return true;
}

inline bool safe_relative_path(const std::string& value, std::string* normalized, std::string* error) {
    if (value.empty()) { *error = "local_path_missing"; return false; }
    const std::filesystem::path path(value);
    if (path.is_absolute() || (value.size() >= 2 && value[1] == ':')) {
        *error = "local_path_must_be_relative";
        return false;
    }
    std::filesystem::path portable;
    std::string converted = value;
    for (char& c : converted) if (c == '\\') c = '/';
    for (const auto& part : std::filesystem::path(converted)) {
        if (part == "." || part.empty()) continue;
        if (part == "..") { *error = "local_path_escape"; return false; }
        portable /= part;
    }
    if (portable.empty()) { *error = "local_path_empty"; return false; }
    *normalized = portable.generic_string();
    return true;
}

}  // namespace av_imgdata::worker::runtime
