#include <vips/vips.h>

#include <algorithm>
#include <cerrno>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Args {
    std::string command;
    std::string input;
    std::string output;
    std::string workdir;
};

struct Job {
    std::string image_path;
    std::string operation;
    std::string output_format = "jpeg";
    std::map<std::string, std::string> options;
};

std::string escape_json(const std::string& value) {
    std::ostringstream out;
    for (char ch : value) {
        switch (ch) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << ch; break;
        }
    }
    return out.str();
}

std::string read_file(const std::string& path) {
    std::ifstream in(path.c_str(), std::ios::in | std::ios::binary);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

bool write_file(const std::string& path, const std::string& body) {
    if (path.empty()) {
        std::cout << body << "\n";
        return true;
    }
    std::ofstream out(path.c_str(), std::ios::out | std::ios::binary);
    if (!out) {
        return false;
    }
    out << body << "\n";
    return true;
}

std::string trim(const std::string& value) {
    const auto start = value.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) {
        return "";
    }
    const auto end = value.find_last_not_of(" \t\r\n");
    return value.substr(start, end - start + 1);
}

std::string json_string_value(const std::string& body, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    const auto key_pos = body.find(needle);
    if (key_pos == std::string::npos) {
        return "";
    }
    const auto colon = body.find(':', key_pos + needle.size());
    if (colon == std::string::npos) {
        return "";
    }
    const auto quote = body.find('"', colon + 1);
    if (quote == std::string::npos) {
        return "";
    }
    std::ostringstream value;
    bool escaped = false;
    for (auto i = quote + 1; i < body.size(); ++i) {
        const char ch = body[i];
        if (escaped) {
            switch (ch) {
                case 'n': value << '\n'; break;
                case 'r': value << '\r'; break;
                case 't': value << '\t'; break;
                default: value << ch; break;
            }
            escaped = false;
            continue;
        }
        if (ch == '\\') {
            escaped = true;
            continue;
        }
        if (ch == '"') {
            break;
        }
        value << ch;
    }
    return value.str();
}

std::string json_object_body(const std::string& body, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    const auto key_pos = body.find(needle);
    if (key_pos == std::string::npos) {
        return "";
    }
    const auto open = body.find('{', key_pos + needle.size());
    if (open == std::string::npos) {
        return "";
    }
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    for (auto i = open; i < body.size(); ++i) {
        const char ch = body[i];
        if (in_string) {
            if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == '"') {
                in_string = false;
            }
            continue;
        }
        if (ch == '"') {
            in_string = true;
        } else if (ch == '{') {
            ++depth;
        } else if (ch == '}') {
            --depth;
            if (depth == 0) {
                return body.substr(open + 1, i - open - 1);
            }
        }
    }
    return "";
}

std::string json_array_body(const std::string& body, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    const auto key_pos = body.find(needle);
    if (key_pos == std::string::npos) {
        return "";
    }
    const auto open = body.find('[', key_pos + needle.size());
    if (open == std::string::npos) {
        return "";
    }
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    for (auto i = open; i < body.size(); ++i) {
        const char ch = body[i];
        if (in_string) {
            if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == '"') {
                in_string = false;
            }
            continue;
        }
        if (ch == '"') {
            in_string = true;
        } else if (ch == '[') {
            ++depth;
        } else if (ch == ']') {
            --depth;
            if (depth == 0) {
                return body.substr(open, i - open + 1);
            }
        }
    }
    return "";
}

std::vector<std::string> json_string_array_value(const std::string& body, const std::string& key) {
    const std::string block = json_array_body(body, key);
    std::vector<std::string> values;
    bool in_string = false;
    bool escaped = false;
    std::ostringstream current;
    for (auto i = 0U; i < block.size(); ++i) {
        const char ch = block[i];
        if (!in_string) {
            if (ch == '"') {
                in_string = true;
                current.str("");
                current.clear();
            }
            continue;
        }
        if (escaped) {
            switch (ch) {
                case 'n': current << '\n'; break;
                case 'r': current << '\r'; break;
                case 't': current << '\t'; break;
                default: current << ch; break;
            }
            escaped = false;
            continue;
        }
        if (ch == '\\') {
            escaped = true;
            continue;
        }
        if (ch == '"') {
            values.push_back(current.str());
            in_string = false;
            continue;
        }
        current << ch;
    }
    return values;
}

int json_int_value(const std::string& body, const std::string& key, int fallback) {
    const std::string text = trim(json_string_value(body, key));
    if (!text.empty()) {
        return std::atoi(text.c_str());
    }
    const std::string needle = "\"" + key + "\"";
    const auto key_pos = body.find(needle);
    if (key_pos == std::string::npos) {
        return fallback;
    }
    const auto colon = body.find(':', key_pos + needle.size());
    if (colon == std::string::npos) {
        return fallback;
    }
    const auto start = body.find_first_of("-0123456789", colon + 1);
    if (start == std::string::npos) {
        return fallback;
    }
    return std::atoi(body.c_str() + start);
}

bool json_bool_value(const std::string& body, const std::string& key, bool fallback) {
    const std::string needle = "\"" + key + "\"";
    const auto key_pos = body.find(needle);
    if (key_pos == std::string::npos) {
        return fallback;
    }
    const auto colon = body.find(':', key_pos + needle.size());
    if (colon == std::string::npos) {
        return fallback;
    }
    const auto value = trim(body.substr(colon + 1, 5));
    if (value.find("true") == 0) {
        return true;
    }
    if (value.find("false") == 0) {
        return false;
    }
    return fallback;
}

Job parse_job(const std::string& path) {
    const std::string body = read_file(path);
    Job job;
    job.image_path = json_string_value(body, "image_path");
    job.operation = json_string_value(body, "operation");
    const std::string format = json_string_value(body, "output_format");
    if (!format.empty()) {
        job.output_format = format;
    }
    const std::string options = json_object_body(body, "options");
    if (!options.empty()) {
        const int width = json_int_value(options, "width", 0);
        const int height = json_int_value(options, "height", 0);
        const int angle = json_int_value(options, "angle", 0);
        const int quality = json_int_value(options, "quality", 95);
        const bool maintain_aspect = json_bool_value(options, "maintain_aspect", true);
        job.options["width"] = std::to_string(width);
        job.options["height"] = std::to_string(height);
        job.options["angle"] = std::to_string(angle);
        job.options["quality"] = std::to_string(std::max(1, std::min(100, quality)));
        job.options["maintain_aspect"] = maintain_aspect ? "true" : "false";
    }
    return job;
}

std::vector<std::string> parse_job_image_paths(const std::string& path) {
    return json_string_array_value(read_file(path), "image_paths");
}

Args parse_args(int argc, char** argv) {
    Args args;
    if (argc > 1) {
        args.command = argv[1];
    }
    for (int i = 2; i < argc; ++i) {
        const std::string flag = argv[i];
        if ((flag == "--input" || flag == "-i") && i + 1 < argc) {
            args.input = argv[++i];
        } else if ((flag == "--output" || flag == "-o" || flag == "--metadata") && i + 1 < argc) {
            args.output = argv[++i];
        } else if ((flag == "--workdir" || flag == "-w") && i + 1 < argc) {
            args.workdir = argv[++i];
        }
    }
    return args;
}

std::string lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

std::string output_extension(const std::string& format) {
    const std::string normalized = lower(format);
    if (normalized == "jpg") {
        return "jpg";
    }
    if (normalized == "png" || normalized == "webp" || normalized == "tiff" || normalized == "tif") {
        return normalized == "tif" ? "tiff" : normalized;
    }
    return "jpeg";
}

bool operation_available(const char* operation) {
    return vips_type_find("VipsOperation", operation) != 0;
}

std::string format_json() {
    std::ostringstream out;
    out << "\"formats\":{"
        << "\"jpeg\":" << (operation_available("jpegload") && operation_available("jpegsave") ? "true" : "false") << ","
        << "\"jpg\":" << (operation_available("jpegload") && operation_available("jpegsave") ? "true" : "false") << ","
        << "\"png\":" << (operation_available("pngload") && operation_available("pngsave") ? "true" : "false") << ","
        << "\"webp\":" << (operation_available("webpload") && operation_available("webpsave") ? "true" : "false") << ","
        << "\"tiff\":" << (operation_available("tiffload") && operation_available("tiffsave") ? "true" : "false") << ","
        << "\"heic\":" << (operation_available("heifload") ? "true" : "false") << ","
        << "\"heif\":" << (operation_available("heifload") ? "true" : "false")
        << "}";
    return out.str();
}

int write_error(const std::string& output, const std::string& operation, const std::string& code, const std::string& message) {
    std::ostringstream json;
    json << "{"
         << "\"success\":false,"
         << "\"contract_version\":\"1.0\","
         << "\"operation\":\"" << escape_json(operation) << "\","
         << "\"error\":\"" << escape_json(code) << "\","
         << "\"message\":\"" << escape_json(message) << "\""
         << "}";
    write_file(output, json.str());
    std::cerr << message << "\n";
    return 1;
}

std::string image_info_json(VipsImage* image, const std::string& operation) {
    int orientation = 1;
    vips_image_get_int(image, "orientation", &orientation);
    const char* interpretation = vips_enum_nick(VIPS_TYPE_INTERPRETATION, vips_image_get_interpretation(image));
    std::ostringstream json;
    json << "{"
         << "\"success\":true,"
         << "\"contract_version\":\"1.0\","
         << "\"operation\":\"" << escape_json(operation) << "\","
         << "\"width\":" << vips_image_get_width(image) << ","
         << "\"height\":" << vips_image_get_height(image) << ","
         << "\"bands\":" << vips_image_get_bands(image) << ","
         << "\"has_alpha\":" << (vips_image_hasalpha(image) ? "true" : "false") << ","
         << "\"orientation\":" << orientation << ","
         << "\"color_space\":\"" << escape_json(interpretation ? interpretation : "") << "\""
         << "}";
    return json.str();
}

int command_probe(const std::string& output) {
    std::ostringstream json;
    json << "{"
         << "\"contract_version\":\"1.0\","
         << "\"processor\":{\"name\":\"av-imgdata-image-processor\",\"backend\":\"libvips\",\"version\":\"0.2.0\"},"
         << "\"backend\":\"libvips\","
         << "\"available\":true,"
         << "\"reason\":\"vips_ready\","
         << format_json()
         << "}";
    return write_file(output, json.str()) ? 0 : 1;
}

int command_info(const Args& args) {
    const std::string input = args.command == "info" ? parse_job(args.input).image_path : args.input;
    VipsImage* image = vips_image_new_from_file(input.c_str(), "access", VIPS_ACCESS_SEQUENTIAL, nullptr);
    if (!image) {
        return write_error(args.output, "info", "image_load_failed", vips_error_buffer());
    }
    const std::string json = image_info_json(image, "info");
    g_object_unref(image);
    return write_file(args.output, json) ? 0 : 1;
}

VipsAngle angle_from_degrees(int degrees) {
    if (degrees == 90) {
        return VIPS_ANGLE_D90;
    }
    if (degrees == 180) {
        return VIPS_ANGLE_D180;
    }
    if (degrees == 270) {
        return VIPS_ANGLE_D270;
    }
    return VIPS_ANGLE_D0;
}

int write_image(VipsImage* image, const std::string& path, int quality) {
    return vips_image_write_to_file(image, path.c_str(), "Q", quality, nullptr);
}

int process_job(const Args& args, const Job& job, const std::string& output_stem) {
    if (job.image_path.empty()) {
        return write_error(args.output, "process", "invalid_job", "image_path missing");
    }
    const std::string operation = job.operation.empty() ? "convert" : job.operation;
    const std::string format = output_extension(job.output_format);
    const std::string out_path = (args.workdir.empty() ? "." : args.workdir) + "/" + output_stem + "." + format;
    const int quality = std::max(1, std::min(100, std::atoi(job.options.count("quality") ? job.options.at("quality").c_str() : "95")));
    VipsImage* image = nullptr;
    VipsImage* processed = nullptr;

    if (operation == "resize") {
        const int width = std::atoi(job.options.count("width") ? job.options.at("width").c_str() : "0");
        const int height = std::atoi(job.options.count("height") ? job.options.at("height").c_str() : "0");
        const bool maintain_aspect = !job.options.count("maintain_aspect") || job.options.at("maintain_aspect") != "false";
        if (width <= 0 && height <= 0) {
            return write_error(args.output, operation, "invalid_resize", "resize requires width or height");
        }
        if (vips_thumbnail(job.image_path.c_str(), &processed, width > 0 ? width : height,
                           "height", height > 0 ? height : width,
                           "size", maintain_aspect ? VIPS_SIZE_DOWN : VIPS_SIZE_FORCE,
                           nullptr)) {
            return write_error(args.output, operation, "resize_failed", vips_error_buffer());
        }
    } else {
        image = vips_image_new_from_file(job.image_path.c_str(), "access", VIPS_ACCESS_SEQUENTIAL, nullptr);
        if (!image) {
            return write_error(args.output, operation, "image_load_failed", vips_error_buffer());
        }
        if (operation == "rotate") {
            const int degrees = std::atoi(job.options.count("angle") ? job.options.at("angle").c_str() : "0");
            if (degrees != 90 && degrees != 180 && degrees != 270) {
                g_object_unref(image);
                return write_error(args.output, operation, "invalid_rotation_angle", "rotate requires 90, 180, or 270 degrees");
            }
            if (vips_rot(image, &processed, angle_from_degrees(degrees), nullptr)) {
                g_object_unref(image);
                return write_error(args.output, operation, "rotate_failed", vips_error_buffer());
            }
        } else if (operation == "auto-orient" || operation == "auto_orient" || operation == "normalize-for-face") {
            if (vips_autorot(image, &processed, nullptr)) {
                g_object_unref(image);
                return write_error(args.output, operation, "auto_orient_failed", vips_error_buffer());
            }
        } else {
            processed = image;
            image = nullptr;
        }
    }

    if (!processed) {
        if (image) {
            g_object_unref(image);
        }
        return write_error(args.output, operation, "processing_failed", "processor did not produce an image");
    }
    if (write_image(processed, out_path, quality)) {
        if (image) {
            g_object_unref(image);
        }
        g_object_unref(processed);
        return write_error(args.output, operation, "output_failed", vips_error_buffer());
    }
    const std::string json = image_info_json(processed, operation).substr(0, image_info_json(processed, operation).size() - 1)
        + ",\"output_path\":\"" + escape_json(out_path) + "\",\"output_format\":\"" + escape_json(format) + "\"}";
    if (image) {
        g_object_unref(image);
    }
    g_object_unref(processed);
    return write_file(args.output, json) ? 0 : 1;
}

int command_process(const Args& args) {
    return process_job(args, parse_job(args.input), "output");
}

int command_process_batch(const Args& args) {
    const Job base_job = parse_job(args.input);
    const std::vector<std::string> image_paths = parse_job_image_paths(args.input);
    if (image_paths.empty()) {
        return write_error(args.output, "process-batch", "invalid_job", "image_paths missing");
    }
    std::ostringstream results;
    results << "[";
    int failed_count = 0;
    for (std::size_t i = 0; i < image_paths.size(); ++i) {
        Job item = base_job;
        item.image_path = image_paths[i];
        Args item_args = args;
        item_args.output = (args.workdir.empty() ? "." : args.workdir) + "/processor-result-" + std::to_string(i) + ".json";
        const int rc = process_job(item_args, item, "output-" + std::to_string(i));
        const std::string item_json = read_file(item_args.output);
        if (rc != 0) {
            ++failed_count;
        }
        if (i) {
            results << ",";
        }
        if (!item_json.empty() && item_json[0] == '{') {
            std::string item_result = item_json;
            const std::size_t last_brace = item_result.find_last_of('}');
            if (last_brace != std::string::npos) {
                item_result = item_result.substr(0, last_brace)
                    + ",\"path\":\"" + escape_json(image_paths[i]) + "\"}";
            }
            results << item_result;
        } else {
            results << "{\"success\":false,\"path\":\"" << escape_json(image_paths[i])
                    << "\",\"error\":\"processor_error\"}";
        }
        std::remove(item_args.output.c_str());
    }
    results << "]";
    std::ostringstream json;
    json << "{"
         << "\"success\":" << (failed_count == static_cast<int>(image_paths.size()) ? "false" : "true") << ","
         << "\"contract_version\":\"1.0\","
         << "\"operation\":\"process-batch\","
         << "\"results\":" << results.str() << ","
         << "\"failed_images\":" << failed_count
         << "}";
    return write_file(args.output, json.str()) ? (failed_count == static_cast<int>(image_paths.size()) ? 1 : 0) : 1;
}

void print_usage() {
    std::cout
        << "av-imgdata-image-processor commands: version, probe, image-info, info, thumbnail, normalize-for-face, process, process-batch, self-test\n";
}

} // namespace

int main(int argc, char** argv) {
    if (VIPS_INIT(argv[0])) {
        std::cerr << vips_error_buffer() << "\n";
        return 1;
    }
    const Args args = parse_args(argc, argv);
    int rc = 0;
    if (args.command == "version") {
        std::cout << "av-imgdata-image-processor 0.2.0 libvips "
                  << vips_version(0) << "." << vips_version(1) << "." << vips_version(2) << "\n";
    } else if (args.command == "probe") {
        rc = command_probe(args.output);
    } else if (args.command == "image-info" || args.command == "info") {
        rc = command_info(args);
    } else if (args.command == "thumbnail" || args.command == "normalize-for-face" || args.command == "process") {
        Args process_args = args;
        if (args.command != "process") {
            const std::string workdir = args.workdir.empty() ? "." : args.workdir;
            const std::string format = output_extension(args.output.empty() ? "jpeg" : args.output.substr(args.output.find_last_of('.') + 1));
            const std::string json_path = workdir + "/av-imgdata-direct-job.json";
            const std::string op = args.command == "thumbnail" ? "resize" : "normalize-for-face";
            std::ofstream job(json_path.c_str());
            job << "{\"image_path\":\"" << escape_json(args.input) << "\",\"operation\":\"" << op
                << "\",\"output_format\":\"" << format << "\",\"options\":{\"width\":512,\"height\":512}}";
            process_args.input = json_path;
            process_args.output = args.output;
        }
        rc = command_process(process_args);
    } else if (args.command == "process-batch") {
        rc = command_process_batch(args);
    } else if (args.command == "self-test") {
        rc = command_probe("");
    } else {
        print_usage();
        rc = args.command.empty() ? 1 : 2;
    }
    vips_shutdown();
    return rc;
}
