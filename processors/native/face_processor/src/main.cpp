#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <csetjmp>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

#include <jpeglib.h>
#ifdef AV_FACE_PROCESSOR_WITH_HEIF
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <dlfcn.h>
#endif
#include <libheif/heif.h>
#endif
#include <onnxruntime_c_api.h>

namespace {

const char* kProcessorName = "av-imgdata-face-processor";
const char* kVersion = "0.5.0-onnxruntime-native-heif";
const char* kBackend = "native";

typedef std::chrono::steady_clock Clock;

double elapsed_ms(const Clock::time_point& start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}

std::string arg_value(const std::vector<std::string>& args, const std::string& name) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i) {
        if (args[i] == name) {
            return args[i + 1];
        }
    }
    return "";
}

bool file_exists(const std::string& path) {
    struct stat st;
    return !path.empty() && stat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode);
}

std::string lowercase(std::string value) {
    for (std::size_t i = 0; i < value.size(); ++i) {
        value[i] = static_cast<char>(std::tolower(static_cast<unsigned char>(value[i])));
    }
    return value;
}

std::string extension_of(const std::string& path) {
    const std::string::size_type slash = path.find_last_of('/');
    const std::string::size_type dot = path.find_last_of('.');
    if (dot == std::string::npos || (slash != std::string::npos && dot < slash)) {
        return "";
    }
    return lowercase(path.substr(dot + 1));
}

bool dir_exists(const std::string& path) {
    struct stat st;
    return !path.empty() && stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

std::string join_path(const std::string& left, const std::string& right) {
    if (left.empty()) {
        return right;
    }
    if (left[left.size() - 1] == '/') {
        return left + right;
    }
    return left + "/" + right;
}

std::string read_text(const std::string& path) {
    std::ifstream in(path.c_str(), std::ios::binary);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

bool write_text(const std::string& path, const std::string& text) {
    std::ofstream out(path.c_str(), std::ios::binary);
    if (!out) {
        return false;
    }
    out << text;
    return static_cast<bool>(out);
}

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (std::size_t i = 0; i < value.size(); ++i) {
        const char ch = value[i];
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

std::string extract_string_after(const std::string& text, const std::string& key) {
    const std::string marker = "\"" + key + "\"";
    std::size_t pos = text.find(marker);
    if (pos == std::string::npos) {
        return "";
    }
    pos = text.find(':', pos + marker.size());
    if (pos == std::string::npos) {
        return "";
    }
    pos = text.find('"', pos + 1);
    if (pos == std::string::npos) {
        return "";
    }
    std::ostringstream value;
    bool escaped = false;
    for (std::size_t i = pos + 1; i < text.size(); ++i) {
        const char ch = text[i];
        if (escaped) {
            value << ch;
            escaped = false;
        } else if (ch == '\\') {
            escaped = true;
        } else if (ch == '"') {
            return value.str();
        } else {
            value << ch;
        }
    }
    return "";
}

std::string extract_array_after(const std::string& text, const std::string& key) {
    const std::string marker = "\"" + key + "\"";
    std::size_t pos = text.find(marker);
    if (pos == std::string::npos) {
        return "";
    }
    pos = text.find('[', pos + marker.size());
    if (pos == std::string::npos) {
        return "";
    }
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    for (std::size_t i = pos; i < text.size(); ++i) {
        const char ch = text[i];
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
                return text.substr(pos, i - pos + 1);
            }
        }
    }
    return "";
}

std::vector<std::string> extract_string_array_after(const std::string& text, const std::string& key) {
    const std::string block = extract_array_after(text, key);
    std::vector<std::string> values;
    bool in_string = false;
    bool escaped = false;
    std::ostringstream current;
    for (std::size_t i = 0; i < block.size(); ++i) {
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
            current << ch;
            escaped = false;
        } else if (ch == '\\') {
            escaped = true;
        } else if (ch == '"') {
            values.push_back(current.str());
            in_string = false;
        } else {
            current << ch;
        }
    }
    return values;
}

std::vector<float> parse_float_values(const std::string& text) {
    std::vector<float> values;
    const char* cursor = text.c_str();
    while (*cursor) {
        char* end = NULL;
        const double value = std::strtod(cursor, &end);
        if (end && end != cursor) {
            values.push_back(static_cast<float>(value));
            cursor = end;
        } else {
            ++cursor;
        }
    }
    return values;
}

std::vector<std::vector<float> > extract_float_matrix_after(const std::string& text, const std::string& key) {
    const std::string block = extract_array_after(text, key);
    std::vector<std::vector<float> > rows;
    std::size_t pos = 0;
    while (pos < block.size()) {
        pos = block.find('[', pos);
        if (pos == std::string::npos) {
            break;
        }
        if (pos == 0) {
            ++pos;
            continue;
        }
        std::size_t end = block.find(']', pos + 1);
        if (end == std::string::npos) {
            break;
        }
        std::vector<float> row = parse_float_values(block.substr(pos + 1, end - pos - 1));
        if (!row.empty()) {
            rows.push_back(row);
        }
        pos = end + 1;
    }
    return rows;
}

struct OrtHandles {
    const OrtApi* api;
    OrtEnv* env;
    OrtSessionOptions* options;

    OrtHandles() : api(OrtGetApiBase()->GetApi(ORT_API_VERSION)), env(NULL), options(NULL) {}

    ~OrtHandles() {
        if (options) {
            api->ReleaseSessionOptions(options);
        }
        if (env) {
            api->ReleaseEnv(env);
        }
    }
};

std::string status_message(const OrtApi* api, OrtStatus* status) {
    if (!status) {
        return "";
    }
    const char* message = api->GetErrorMessage(status);
    std::string result = message ? message : "onnxruntime error";
    api->ReleaseStatus(status);
    return result;
}

bool create_session(OrtHandles& ort, const std::string& model_path, std::string* error) {
    OrtSession* session = NULL;
    OrtStatus* status = ort.api->CreateSession(ort.env, model_path.c_str(), ort.options, &session);
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }
    ort.api->ReleaseSession(session);
    return true;
}

std::string model_dir(const std::string& model_root, const std::string& model_name) {
    const std::string direct = join_path(model_root, model_name);
    if (dir_exists(direct)) {
        return direct;
    }
    return join_path(join_path(model_root, "models"), model_name);
}

struct ModelPaths {
    std::string detector;
    std::string recognizer;
};

ModelPaths resolve_models(const std::string& model_root, const std::string& model_name) {
    const std::string dir = model_dir(model_root, model_name);
    ModelPaths paths;
    paths.detector = join_path(dir, "det_10g.onnx");
    paths.recognizer = join_path(dir, "w600k_r50.onnx");
    return paths;
}

double extract_number_after(const std::string& text, const std::string& key, double fallback) {
    const std::string marker = "\"" + key + "\"";
    std::size_t pos = text.find(marker);
    if (pos == std::string::npos) {
        return fallback;
    }
    pos = text.find(':', pos + marker.size());
    if (pos == std::string::npos) {
        return fallback;
    }
    char* end = NULL;
    const double value = std::strtod(text.c_str() + pos + 1, &end);
    return end && end != text.c_str() + pos + 1 ? value : fallback;
}

int extract_int_after(const std::string& text, const std::string& key, int fallback) {
    return static_cast<int>(extract_number_after(text, key, fallback));
}

int env_int(const char* name, int fallback, int minimum, int maximum) {
    const char* raw = getenv(name);
    if (!raw || !*raw) {
        return fallback;
    }
    char* end = NULL;
    const long value = std::strtol(raw, &end, 10);
    if (!end || end == raw) {
        return fallback;
    }
    return static_cast<int>(std::max<long>(minimum, std::min<long>(maximum, value)));
}

std::string env_lower(const char* name, const std::string& fallback) {
    const char* raw = getenv(name);
    if (!raw || !*raw) {
        return fallback;
    }
    return lowercase(std::string(raw));
}

int configured_ort_intra_threads() {
    return env_int("AV_IMGDATA_ORT_INTRA_THREADS", 0, 0, 64);
}

GraphOptimizationLevel configured_ort_graph_level() {
    const std::string level = env_lower("AV_IMGDATA_ORT_GRAPH_OPT_LEVEL", "all");
    if (level == "disable" || level == "disabled" || level == "none") {
        return ORT_DISABLE_ALL;
    }
    if (level == "basic") {
        return ORT_ENABLE_BASIC;
    }
    if (level == "extended") {
        return ORT_ENABLE_EXTENDED;
    }
    return ORT_ENABLE_ALL;
}

std::string configured_ort_graph_level_name() {
    const std::string level = env_lower("AV_IMGDATA_ORT_GRAPH_OPT_LEVEL", "all");
    if (level == "disable" || level == "disabled" || level == "none") {
        return "disable";
    }
    if (level == "basic" || level == "extended" || level == "all") {
        return level;
    }
    return "all";
}

struct Image {
    int width;
    int height;
    std::vector<unsigned char> rgb;
};

struct JpegErrorManager {
    jpeg_error_mgr pub;
    jmp_buf jump;
};

extern "C" void jpeg_error_exit_handler(j_common_ptr cinfo) {
    JpegErrorManager* mgr = reinterpret_cast<JpegErrorManager*>(cinfo->err);
    longjmp(mgr->jump, 1);
}

bool decode_jpeg(const std::string& path, Image* image, std::string* error) {
    FILE* file = fopen(path.c_str(), "rb");
    if (!file) {
        *error = "image could not be opened: " + path;
        return false;
    }

    jpeg_decompress_struct cinfo;
    JpegErrorManager jerr;
    cinfo.err = jpeg_std_error(&jerr.pub);
    jerr.pub.error_exit = jpeg_error_exit_handler;
    if (setjmp(jerr.jump)) {
        jpeg_destroy_decompress(&cinfo);
        fclose(file);
        *error = "jpeg decode failed: " + path;
        return false;
    }

    jpeg_create_decompress(&cinfo);
    jpeg_stdio_src(&cinfo, file);
    jpeg_read_header(&cinfo, TRUE);
    cinfo.out_color_space = JCS_RGB;
    jpeg_start_decompress(&cinfo);
    image->width = static_cast<int>(cinfo.output_width);
    image->height = static_cast<int>(cinfo.output_height);
    image->rgb.assign(static_cast<std::size_t>(image->width) * image->height * 3, 0);
    while (cinfo.output_scanline < cinfo.output_height) {
        unsigned char* row = &image->rgb[static_cast<std::size_t>(cinfo.output_scanline) * image->width * 3];
        jpeg_read_scanlines(&cinfo, &row, 1);
    }
    jpeg_finish_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);
    fclose(file);
    return image->width > 0 && image->height > 0;
}

#ifdef AV_FACE_PROCESSOR_WITH_HEIF
std::string windows_library_error_message() {
#ifdef _WIN32
    DWORD error_code = GetLastError();
    if (error_code == 0) {
        return "Windows loader failed";
    }
    char* message = NULL;
    DWORD length = FormatMessageA(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        NULL,
        error_code,
        MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
        reinterpret_cast<LPSTR>(&message),
        0,
        NULL
    );
    std::string result = "Windows loader error " + std::to_string(static_cast<unsigned long>(error_code));
    if (length && message) {
        result += ": ";
        result += message;
    }
    if (message) {
        LocalFree(message);
    }
    return result;
#else
    return "";
#endif
}

std::string heif_error_message(const std::string& prefix, const heif_error& heif_error_value) {
    std::ostringstream out;
    out << prefix << ": code=" << static_cast<int>(heif_error_value.code)
        << " subcode=" << static_cast<int>(heif_error_value.subcode);
    if (heif_error_value.message && heif_error_value.message[0]) {
        out << " message=" << heif_error_value.message;
    }
    return out.str();
}

#ifdef _WIN32
typedef HMODULE HeifLibraryHandle;

template <typename T>
bool load_heif_symbol(HeifLibraryHandle handle, const char* name, T* target, std::string* error) {
    FARPROC symbol = GetProcAddress(handle, name);
    if (!symbol) {
        if (error) {
            *error = std::string("missing libheif symbol ") + name + ": " + windows_library_error_message();
        }
        return false;
    }
    *target = reinterpret_cast<T>(symbol);
    return true;
}
#else
typedef void* HeifLibraryHandle;

template <typename T>
bool load_heif_symbol(HeifLibraryHandle handle, const char* name, T* target, std::string* error) {
    dlerror();
    void* symbol = dlsym(handle, name);
    const char* symbol_error = dlerror();
    if (symbol_error || !symbol) {
        if (error) {
            *error = std::string("missing libheif symbol ") + name + (symbol_error ? std::string(": ") + symbol_error : "");
        }
        return false;
    }
    *target = reinterpret_cast<T>(symbol);
    return true;
}
#endif

struct HeifApi {
    typedef heif_context* (*ContextAllocFn)(void);
    typedef void (*ContextFreeFn)(heif_context*);
    typedef heif_error (*ContextReadFromFileFn)(heif_context*, const char*, const heif_reading_options*);
    typedef heif_error (*ContextGetPrimaryImageHandleFn)(heif_context*, heif_image_handle**);
    typedef void (*ImageHandleReleaseFn)(const heif_image_handle*);
    typedef heif_error (*DecodeImageFn)(const heif_image_handle*, heif_image**, heif_colorspace, heif_chroma, const heif_decoding_options*);
    typedef int (*ImageGetWidthFn)(const heif_image*, heif_channel);
    typedef int (*ImageGetHeightFn)(const heif_image*, heif_channel);
    typedef const uint8_t* (*ImageGetPlaneReadonlyFn)(const heif_image*, heif_channel, int*);
    typedef void (*ImageReleaseFn)(heif_image*);
    typedef int (*HaveDecoderForFormatFn)(heif_compression_format);

    HeifLibraryHandle handle;
    bool attempted;
    std::string load_error;
    ContextAllocFn context_alloc;
    ContextFreeFn context_free;
    ContextReadFromFileFn context_read_from_file;
    ContextGetPrimaryImageHandleFn context_get_primary_image_handle;
    ImageHandleReleaseFn image_handle_release;
    DecodeImageFn decode_image;
    ImageGetWidthFn image_get_width;
    ImageGetHeightFn image_get_height;
    ImageGetPlaneReadonlyFn image_get_plane_readonly;
    ImageReleaseFn image_release;
    HaveDecoderForFormatFn have_decoder_for_format;

    HeifApi()
        : handle(NULL), attempted(false), context_alloc(NULL), context_free(NULL), context_read_from_file(NULL),
          context_get_primary_image_handle(NULL), image_handle_release(NULL), decode_image(NULL), image_get_width(NULL),
          image_get_height(NULL), image_get_plane_readonly(NULL), image_release(NULL), have_decoder_for_format(NULL) {}

    bool load(std::string* error) {
        if (handle) {
            return true;
        }
        if (attempted) {
            if (error) {
                *error = load_error;
            }
            return false;
        }
        attempted = true;

        std::vector<std::string> candidates;
        const char* configured = getenv("AV_IMGDATA_LIBHEIF");
        if (configured && *configured) {
            candidates.push_back(configured);
        }
#ifdef _WIN32
        candidates.push_back("libheif.dll");
        candidates.push_back("heif.dll");
#else
        candidates.push_back("libheif.so.1");
        candidates.push_back("libheif.so");
#endif

        std::ostringstream errors;
        for (std::size_t i = 0; i < candidates.size(); ++i) {
            HeifLibraryHandle candidate = NULL;
#ifdef _WIN32
            candidate = LoadLibraryA(candidates[i].c_str());
#else
            candidate = dlopen(candidates[i].c_str(), RTLD_LAZY | RTLD_LOCAL);
#endif
            if (!candidate) {
#ifdef _WIN32
                errors << candidates[i] << ": " << windows_library_error_message() << "; ";
#else
                const char* open_error = dlerror();
                errors << candidates[i] << ": " << (open_error ? open_error : "dlopen failed") << "; ";
#endif
                continue;
            }

            std::string symbol_error;
            if (load_heif_symbol(candidate, "heif_context_alloc", &context_alloc, &symbol_error)
                    && load_heif_symbol(candidate, "heif_context_free", &context_free, &symbol_error)
                    && load_heif_symbol(candidate, "heif_context_read_from_file", &context_read_from_file, &symbol_error)
                    && load_heif_symbol(candidate, "heif_context_get_primary_image_handle", &context_get_primary_image_handle, &symbol_error)
                    && load_heif_symbol(candidate, "heif_image_handle_release", &image_handle_release, &symbol_error)
                    && load_heif_symbol(candidate, "heif_decode_image", &decode_image, &symbol_error)
                    && load_heif_symbol(candidate, "heif_image_get_width", &image_get_width, &symbol_error)
                    && load_heif_symbol(candidate, "heif_image_get_height", &image_get_height, &symbol_error)
                    && load_heif_symbol(candidate, "heif_image_get_plane_readonly", &image_get_plane_readonly, &symbol_error)
                    && load_heif_symbol(candidate, "heif_image_release", &image_release, &symbol_error)
                    && load_heif_symbol(candidate, "heif_have_decoder_for_format", &have_decoder_for_format, &symbol_error)) {
                handle = candidate;
                return true;
            }
#ifdef _WIN32
            FreeLibrary(candidate);
#else
            dlclose(candidate);
#endif
            errors << candidates[i] << ": " << symbol_error << "; ";
        }

        load_error = errors.str();
        if (load_error.empty()) {
            load_error = "libheif runtime library not found";
        }
        if (error) {
            *error = load_error;
        }
        return false;
    }
};

HeifApi& heif_api() {
    static HeifApi api;
    return api;
}

#endif

bool heif_decoder_available(std::string* reason) {
#ifdef AV_FACE_PROCESSOR_WITH_HEIF
    HeifApi& api = heif_api();
    std::string load_error;
    if (!api.load(&load_error)) {
        if (reason) {
            *reason = "libheif runtime loader unavailable: " + load_error;
        }
        return false;
    }
    const int hevc_available = api.have_decoder_for_format(heif_compression_HEVC);
    const int av1_available = api.have_decoder_for_format(heif_compression_AV1);
    if (hevc_available || av1_available) {
        return true;
    }
    if (reason) {
        *reason = "libheif is linked, but no HEVC or AV1 decoder is available";
    }
    return false;
#else
    if (reason) {
        *reason = "libheif headers were not available when the native processor was built";
    }
    return false;
#endif
}

bool decode_heif(const std::string& path, Image* image, std::string* error) {
#ifdef AV_FACE_PROCESSOR_WITH_HEIF
    std::string decoder_reason;
    if (!heif_decoder_available(&decoder_reason)) {
        *error = decoder_reason + ": " + path;
        return false;
    }
    HeifApi& api = heif_api();

    heif_context* ctx = api.context_alloc();
    if (!ctx) {
        *error = "heif context allocation failed: " + path;
        return false;
    }

    heif_error heif_status = api.context_read_from_file(ctx, path.c_str(), NULL);
    if (heif_status.code != heif_error_Ok) {
        *error = heif_error_message("heif read failed", heif_status) + ": " + path;
        api.context_free(ctx);
        return false;
    }

    heif_image_handle* handle = NULL;
    heif_status = api.context_get_primary_image_handle(ctx, &handle);
    if (heif_status.code != heif_error_Ok || !handle) {
        *error = heif_error_message("heif primary image missing", heif_status) + ": " + path;
        api.context_free(ctx);
        return false;
    }

    heif_image* decoded = NULL;
    heif_status = api.decode_image(handle, &decoded, heif_colorspace_RGB, heif_chroma_interleaved_RGB, NULL);
    if (heif_status.code != heif_error_Ok || !decoded) {
        *error = heif_error_message("heif decode failed", heif_status) + ": " + path;
        api.image_handle_release(handle);
        api.context_free(ctx);
        return false;
    }

    const int width = api.image_get_width(decoded, heif_channel_interleaved);
    const int height = api.image_get_height(decoded, heif_channel_interleaved);
    int stride = 0;
    const uint8_t* plane = api.image_get_plane_readonly(decoded, heif_channel_interleaved, &stride);
    if (width <= 0 || height <= 0 || stride <= 0 || !plane) {
        *error = "heif decoded image has no RGB plane: " + path;
        api.image_release(decoded);
        api.image_handle_release(handle);
        api.context_free(ctx);
        return false;
    }

    image->width = width;
    image->height = height;
    image->rgb.assign(static_cast<std::size_t>(width) * height * 3, 0);
    for (int y = 0; y < height; ++y) {
        const uint8_t* source = plane + static_cast<std::size_t>(y) * stride;
        unsigned char* target = &image->rgb[static_cast<std::size_t>(y) * width * 3];
        std::copy(source, source + static_cast<std::size_t>(width) * 3, target);
    }

    api.image_release(decoded);
    api.image_handle_release(handle);
    api.context_free(ctx);
    return true;
#else
    *error = "libheif headers were not available when the native processor was built: " + path;
    return false;
#endif
}

bool decode_image(const std::string& path, Image* image, std::string* error) {
    const std::string extension = extension_of(path);
    if (extension == "heic" || extension == "heif") {
        return decode_heif(path, image, error);
    }
    return decode_jpeg(path, image, error);
}

float bilinear_sample(const Image& image, float x, float y, int channel) {
    if (image.width <= 0 || image.height <= 0) {
        return 0.0f;
    }
    x = std::max(0.0f, std::min(x, static_cast<float>(image.width - 1)));
    y = std::max(0.0f, std::min(y, static_cast<float>(image.height - 1)));
    const int x0 = static_cast<int>(std::floor(x));
    const int y0 = static_cast<int>(std::floor(y));
    const int x1 = std::min(x0 + 1, image.width - 1);
    const int y1 = std::min(y0 + 1, image.height - 1);
    const float dx = x - x0;
    const float dy = y - y0;
    const std::size_t i00 = (static_cast<std::size_t>(y0) * image.width + x0) * 3 + channel;
    const std::size_t i10 = (static_cast<std::size_t>(y0) * image.width + x1) * 3 + channel;
    const std::size_t i01 = (static_cast<std::size_t>(y1) * image.width + x0) * 3 + channel;
    const std::size_t i11 = (static_cast<std::size_t>(y1) * image.width + x1) * 3 + channel;
    const float top = image.rgb[i00] * (1.0f - dx) + image.rgb[i10] * dx;
    const float bottom = image.rgb[i01] * (1.0f - dx) + image.rgb[i11] * dx;
    return top * (1.0f - dy) + bottom * dy;
}

struct PreparedImage {
    int input_width;
    int input_height;
    int resized_width;
    int resized_height;
    float det_scale;
    std::vector<float> nchw;
};

PreparedImage prepare_detector_input(const Image& image, int input_width, int input_height) {
    PreparedImage prepared;
    prepared.input_width = input_width;
    prepared.input_height = input_height;
    const float image_ratio = static_cast<float>(image.height) / std::max(1, image.width);
    const float model_ratio = static_cast<float>(input_height) / std::max(1, input_width);
    if (image_ratio > model_ratio) {
        prepared.resized_height = input_height;
        prepared.resized_width = std::max(1, static_cast<int>(input_height / image_ratio));
    } else {
        prepared.resized_width = input_width;
        prepared.resized_height = std::max(1, static_cast<int>(input_width * image_ratio));
    }
    prepared.det_scale = static_cast<float>(prepared.resized_height) / std::max(1, image.height);
    prepared.nchw.assign(static_cast<std::size_t>(3) * input_height * input_width, 0.0f);
    for (int y = 0; y < prepared.resized_height; ++y) {
        const float src_y = (static_cast<float>(y) + 0.5f) * image.height / prepared.resized_height - 0.5f;
        for (int x = 0; x < prepared.resized_width; ++x) {
            const float src_x = (static_cast<float>(x) + 0.5f) * image.width / prepared.resized_width - 0.5f;
            for (int c = 0; c < 3; ++c) {
                const float pixel = bilinear_sample(image, src_x, src_y, c);
                prepared.nchw[(static_cast<std::size_t>(c) * input_height + y) * input_width + x] = (pixel - 127.5f) / 128.0f;
            }
        }
    }
    return prepared;
}

struct TensorData {
    std::vector<int64_t> shape;
    std::vector<float> values;
};

struct OnnxSession {
    OrtHandles* ort;
    OrtSession* session;
    std::string input_name;
    std::vector<std::string> output_names;

    OnnxSession() : ort(NULL), session(NULL) {}
    ~OnnxSession() {
        if (session && ort) {
            ort->api->ReleaseSession(session);
        }
    }
};

bool load_session(OrtHandles& ort, const std::string& model_path, OnnxSession* loaded, std::string* error) {
    loaded->ort = &ort;
    OrtStatus* status = ort.api->CreateSession(ort.env, model_path.c_str(), ort.options, &loaded->session);
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }
    OrtAllocator* allocator = NULL;
    status = ort.api->GetAllocatorWithDefaultOptions(&allocator);
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }
    char* input_name = NULL;
    status = ort.api->SessionGetInputName(loaded->session, 0, allocator, &input_name);
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }
    loaded->input_name = input_name ? input_name : "";
    status = ort.api->AllocatorFree(allocator, input_name);
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }
    size_t output_count = 0;
    status = ort.api->SessionGetOutputCount(loaded->session, &output_count);
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }
    for (size_t i = 0; i < output_count; ++i) {
        char* output_name = NULL;
        status = ort.api->SessionGetOutputName(loaded->session, i, allocator, &output_name);
        if (status) {
            *error = status_message(ort.api, status);
            return false;
        }
        loaded->output_names.push_back(output_name ? output_name : "");
        status = ort.api->AllocatorFree(allocator, output_name);
        if (status) {
            *error = status_message(ort.api, status);
            return false;
        }
    }
    return !loaded->input_name.empty() && !loaded->output_names.empty();
}

bool run_session(OnnxSession& session, const std::vector<float>& input, const std::vector<int64_t>& input_shape, std::vector<TensorData>* outputs, std::string* error) {
    const OrtApi* api = session.ort->api;
    OrtMemoryInfo* memory_info = NULL;
    OrtStatus* status = api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &memory_info);
    if (status) {
        *error = status_message(api, status);
        return false;
    }
    OrtValue* input_tensor = NULL;
    status = api->CreateTensorWithDataAsOrtValue(
        memory_info,
        const_cast<float*>(input.data()),
        input.size() * sizeof(float),
        input_shape.data(),
        input_shape.size(),
        ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT,
        &input_tensor
    );
    api->ReleaseMemoryInfo(memory_info);
    if (status) {
        *error = status_message(api, status);
        return false;
    }
    std::vector<const char*> output_names;
    for (std::size_t i = 0; i < session.output_names.size(); ++i) {
        output_names.push_back(session.output_names[i].c_str());
    }
    const char* input_names[] = {session.input_name.c_str()};
    std::vector<OrtValue*> raw_outputs(output_names.size(), NULL);
    status = api->Run(
        session.session,
        NULL,
        input_names,
        const_cast<const OrtValue* const*>(&input_tensor),
        1,
        output_names.data(),
        output_names.size(),
        raw_outputs.data()
    );
    api->ReleaseValue(input_tensor);
    if (status) {
        *error = status_message(api, status);
        return false;
    }
    outputs->clear();
    for (std::size_t i = 0; i < raw_outputs.size(); ++i) {
        OrtTensorTypeAndShapeInfo* info = NULL;
        status = api->GetTensorTypeAndShape(raw_outputs[i], &info);
        if (status) {
            *error = status_message(api, status);
            return false;
        }
        size_t dim_count = 0;
        status = api->GetDimensionsCount(info, &dim_count);
        if (status) {
            *error = status_message(api, status);
            return false;
        }
        TensorData tensor;
        tensor.shape.assign(dim_count, 0);
        status = api->GetDimensions(info, tensor.shape.data(), dim_count);
        if (status) {
            *error = status_message(api, status);
            return false;
        }
        size_t element_count = 0;
        status = api->GetTensorShapeElementCount(info, &element_count);
        if (status) {
            *error = status_message(api, status);
            return false;
        }
        api->ReleaseTensorTypeAndShapeInfo(info);
        float* data = NULL;
        status = api->GetTensorMutableData(raw_outputs[i], reinterpret_cast<void**>(&data));
        if (status) {
            *error = status_message(api, status);
            return false;
        }
        tensor.values.assign(data, data + element_count);
        outputs->push_back(tensor);
        api->ReleaseValue(raw_outputs[i]);
    }
    return true;
}

struct FaceCandidate {
    float x1;
    float y1;
    float x2;
    float y2;
    float score;
    float landmarks[10];
    std::vector<float> embedding;
};

struct InferenceTiming {
    double total_ms;
    double image_decode_ms;
    double model_load_ms;
    double detector_prepare_ms;
    double detector_run_ms;
    double detector_decode_ms;
    double recognizer_prepare_ms;
    double recognizer_run_ms;
    double embedding_normalize_ms;
    double result_write_ms;
    int recognizer_runs;
    int recognized_faces;
    int recognizer_batch_size;
    bool recognizer_batched;
    bool recognizer_batch_fallback;
    bool reused_models;

    InferenceTiming()
        : total_ms(0.0), image_decode_ms(0.0), model_load_ms(0.0), detector_prepare_ms(0.0),
          detector_run_ms(0.0), detector_decode_ms(0.0), recognizer_prepare_ms(0.0),
          recognizer_run_ms(0.0), embedding_normalize_ms(0.0), result_write_ms(0.0),
          recognizer_runs(0), recognized_faces(0), recognizer_batch_size(0), recognizer_batched(false),
          recognizer_batch_fallback(false), reused_models(false) {}
};

std::string timing_json(const InferenceTiming& timing) {
    std::ostringstream out;
    out << "{"
        << "\"total\":" << timing.total_ms
        << ",\"image_decode\":" << timing.image_decode_ms
        << ",\"model_load\":" << timing.model_load_ms
        << ",\"detector_prepare\":" << timing.detector_prepare_ms
        << ",\"detector_run\":" << timing.detector_run_ms
        << ",\"detector_decode\":" << timing.detector_decode_ms
        << ",\"recognizer_prepare\":" << timing.recognizer_prepare_ms
        << ",\"recognizer_run\":" << timing.recognizer_run_ms
        << ",\"embedding_normalize\":" << timing.embedding_normalize_ms
        << ",\"result_write\":" << timing.result_write_ms
        << ",\"recognizer_runs\":" << timing.recognizer_runs
        << ",\"recognized_faces\":" << timing.recognized_faces
        << ",\"recognizer_batch_size\":" << timing.recognizer_batch_size
        << ",\"recognizer_batched\":" << (timing.recognizer_batched ? "true" : "false")
        << ",\"recognizer_batch_fallback\":" << (timing.recognizer_batch_fallback ? "true" : "false")
        << ",\"reused_models\":" << (timing.reused_models ? "true" : "false")
        << "}";
    return out.str();
}

float iou(const FaceCandidate& left, const FaceCandidate& right) {
    const float x1 = std::max(left.x1, right.x1);
    const float y1 = std::max(left.y1, right.y1);
    const float x2 = std::min(left.x2, right.x2);
    const float y2 = std::min(left.y2, right.y2);
    const float intersection = std::max(0.0f, x2 - x1) * std::max(0.0f, y2 - y1);
    const float left_area = std::max(0.0f, left.x2 - left.x1) * std::max(0.0f, left.y2 - left.y1);
    const float right_area = std::max(0.0f, right.x2 - right.x1) * std::max(0.0f, right.y2 - right.y1);
    const float union_area = left_area + right_area - intersection;
    return union_area > 0.0f ? intersection / union_area : 0.0f;
}

std::vector<FaceCandidate> nms(std::vector<FaceCandidate> faces, float threshold, int max_faces) {
    std::sort(faces.begin(), faces.end(), [](const FaceCandidate& a, const FaceCandidate& b) { return a.score > b.score; });
    std::vector<FaceCandidate> kept;
    std::vector<char> suppressed(faces.size(), 0);
    for (std::size_t i = 0; i < faces.size(); ++i) {
        if (suppressed[i]) {
            continue;
        }
        kept.push_back(faces[i]);
        if (max_faces > 0 && static_cast<int>(kept.size()) >= max_faces) {
            break;
        }
        for (std::size_t j = i + 1; j < faces.size(); ++j) {
            if (!suppressed[j] && iou(faces[i], faces[j]) > threshold) {
                suppressed[j] = 1;
            }
        }
    }
    return kept;
}

int tensor_rows(const TensorData& tensor) {
    if (tensor.shape.size() >= 2) {
        return static_cast<int>(tensor.shape[tensor.shape.size() - 2]);
    }
    return 0;
}

int tensor_cols(const TensorData& tensor) {
    if (!tensor.shape.empty()) {
        return static_cast<int>(tensor.shape[tensor.shape.size() - 1]);
    }
    return 0;
}

float tensor_value(const TensorData& tensor, int row, int col) {
    const int cols = std::max(1, tensor_cols(tensor));
    const std::size_t index = static_cast<std::size_t>(row) * cols + col;
    return index < tensor.values.size() ? tensor.values[index] : 0.0f;
}

std::vector<FaceCandidate> decode_scrfd(const std::vector<TensorData>& outputs, const PreparedImage& prepared, const Image& image, float min_score, int max_faces) {
    std::vector<FaceCandidate> candidates;
    if (outputs.size() < 6) {
        return candidates;
    }
    const int strides[3] = {8, 16, 32};
    for (int level = 0; level < 3; ++level) {
        const TensorData& scores = outputs[level];
        const TensorData& boxes = outputs[level + 3];
        const TensorData* kps = outputs.size() >= 9 ? &outputs[level + 6] : NULL;
        const int rows = std::min(tensor_rows(scores), tensor_rows(boxes));
        const int cols = tensor_cols(scores);
        const int stride = strides[level];
        const int feature_w = prepared.input_width / stride;
        for (int row = 0; row < rows; ++row) {
            float score = cols > 1 ? std::max(tensor_value(scores, row, 0), tensor_value(scores, row, 1)) : tensor_value(scores, row, 0);
            if (score < min_score) {
                continue;
            }
            const int anchor_index = row / 2;
            const int anchor_y = anchor_index / std::max(1, feature_w);
            const int anchor_x = anchor_index % std::max(1, feature_w);
            const float cx = (static_cast<float>(anchor_x) + 0.5f) * stride;
            const float cy = (static_cast<float>(anchor_y) + 0.5f) * stride;
            FaceCandidate face;
            face.x1 = (cx - tensor_value(boxes, row, 0) * stride) / prepared.det_scale;
            face.y1 = (cy - tensor_value(boxes, row, 1) * stride) / prepared.det_scale;
            face.x2 = (cx + tensor_value(boxes, row, 2) * stride) / prepared.det_scale;
            face.y2 = (cy + tensor_value(boxes, row, 3) * stride) / prepared.det_scale;
            face.x1 = std::max(0.0f, std::min(face.x1, static_cast<float>(image.width)));
            face.y1 = std::max(0.0f, std::min(face.y1, static_cast<float>(image.height)));
            face.x2 = std::max(0.0f, std::min(face.x2, static_cast<float>(image.width)));
            face.y2 = std::max(0.0f, std::min(face.y2, static_cast<float>(image.height)));
            if (face.x2 <= face.x1 || face.y2 <= face.y1) {
                continue;
            }
            face.score = score;
            for (int i = 0; i < 10; ++i) {
                face.landmarks[i] = 0.0f;
            }
            if (kps && tensor_cols(*kps) >= 10) {
                for (int point = 0; point < 5; ++point) {
                    face.landmarks[point * 2] = (cx + tensor_value(*kps, row, point * 2) * stride) / prepared.det_scale;
                    face.landmarks[point * 2 + 1] = (cy + tensor_value(*kps, row, point * 2 + 1) * stride) / prepared.det_scale;
                }
            }
            candidates.push_back(face);
        }
    }
    return nms(candidates, 0.4f, max_faces);
}

bool estimate_similarity(const FaceCandidate& face, double matrix[6]) {
    const double src[10] = {
        face.landmarks[0], face.landmarks[1], face.landmarks[2], face.landmarks[3], face.landmarks[4],
        face.landmarks[5], face.landmarks[6], face.landmarks[7], face.landmarks[8], face.landmarks[9]
    };
    const double dst[10] = {38.2946, 51.6963, 73.5318, 51.5014, 56.0252, 71.7366, 41.5493, 92.3655, 70.7299, 92.2041};
    double src_cx = 0.0, src_cy = 0.0, dst_cx = 0.0, dst_cy = 0.0;
    for (int i = 0; i < 5; ++i) {
        src_cx += src[i * 2];
        src_cy += src[i * 2 + 1];
        dst_cx += dst[i * 2];
        dst_cy += dst[i * 2 + 1];
    }
    src_cx /= 5.0; src_cy /= 5.0; dst_cx /= 5.0; dst_cy /= 5.0;
    double a = 0.0, b = 0.0, denom = 0.0;
    for (int i = 0; i < 5; ++i) {
        const double sx = src[i * 2] - src_cx;
        const double sy = src[i * 2 + 1] - src_cy;
        const double dx = dst[i * 2] - dst_cx;
        const double dy = dst[i * 2 + 1] - dst_cy;
        a += sx * dx + sy * dy;
        b += sx * dy - sy * dx;
        denom += sx * sx + sy * sy;
    }
    if (denom <= 0.0) {
        return false;
    }
    a /= denom;
    b /= denom;
    matrix[0] = a;
    matrix[1] = -b;
    matrix[2] = dst_cx - a * src_cx + b * src_cy;
    matrix[3] = b;
    matrix[4] = a;
    matrix[5] = dst_cy - b * src_cx - a * src_cy;
    return true;
}

std::vector<float> prepare_recognition_input(const Image& image, const FaceCandidate& face) {
    double forward[6];
    std::vector<float> input(static_cast<std::size_t>(3) * 112 * 112, 0.0f);
    if (!estimate_similarity(face, forward)) {
        return input;
    }
    const double det = forward[0] * forward[4] - forward[1] * forward[3];
    if (std::fabs(det) < 1e-8) {
        return input;
    }
    const double inv[6] = {
        forward[4] / det,
        -forward[1] / det,
        (forward[1] * forward[5] - forward[4] * forward[2]) / det,
        -forward[3] / det,
        forward[0] / det,
        (forward[3] * forward[2] - forward[0] * forward[5]) / det
    };
    for (int y = 0; y < 112; ++y) {
        for (int x = 0; x < 112; ++x) {
            const float src_x = static_cast<float>(inv[0] * x + inv[1] * y + inv[2]);
            const float src_y = static_cast<float>(inv[3] * x + inv[4] * y + inv[5]);
            for (int c = 0; c < 3; ++c) {
                const float pixel = bilinear_sample(image, src_x, src_y, c);
                input[(static_cast<std::size_t>(c) * 112 + y) * 112 + x] = (pixel - 127.5f) / 127.5f;
            }
        }
    }
    return input;
}

std::vector<float> prepare_recognition_batch_input(const Image& image, const std::vector<FaceCandidate>& faces) {
    std::vector<float> batch;
    batch.reserve(faces.size() * 3 * 112 * 112);
    for (std::size_t i = 0; i < faces.size(); ++i) {
        const std::vector<float> input = prepare_recognition_input(image, faces[i]);
        batch.insert(batch.end(), input.begin(), input.end());
    }
    return batch;
}

void normalize_vector(std::vector<float>* values) {
    double sum = 0.0;
    for (std::size_t i = 0; i < values->size(); ++i) {
        sum += static_cast<double>((*values)[i]) * (*values)[i];
    }
    const double norm = std::sqrt(sum);
    if (norm <= 0.0) {
        return;
    }
    for (std::size_t i = 0; i < values->size(); ++i) {
        (*values)[i] = static_cast<float>((*values)[i] / norm);
    }
}

float vector_similarity(const std::vector<float>& left, const std::vector<float>& right) {
    const std::size_t size = std::min(left.size(), right.size());
    double score = 0.0;
    for (std::size_t i = 0; i < size; ++i) {
        score += static_cast<double>(left[i]) * static_cast<double>(right[i]);
    }
    return static_cast<float>(score);
}

std::vector<float> centroid_vector(const std::vector<std::vector<float> >& embeddings) {
    if (embeddings.empty() || embeddings[0].empty()) {
        return std::vector<float>();
    }
    const std::size_t size = embeddings[0].size();
    std::vector<float> centroid(size, 0.0f);
    int used = 0;
    for (std::size_t row = 0; row < embeddings.size(); ++row) {
        if (embeddings[row].size() != size) {
            continue;
        }
        for (std::size_t col = 0; col < size; ++col) {
            centroid[col] += embeddings[row][col];
        }
        ++used;
    }
    if (used <= 0) {
        return std::vector<float>();
    }
    for (std::size_t col = 0; col < size; ++col) {
        centroid[col] /= static_cast<float>(used);
    }
    normalize_vector(&centroid);
    return centroid;
}

int medoid_index(const std::vector<std::vector<float> >& embeddings) {
    if (embeddings.size() <= 1) {
        return 0;
    }
    std::vector<std::vector<float> > normalized = embeddings;
    for (std::size_t i = 0; i < normalized.size(); ++i) {
        normalize_vector(&normalized[i]);
    }
    int best_index = 0;
    float best_score = -std::numeric_limits<float>::infinity();
    for (std::size_t i = 0; i < normalized.size(); ++i) {
        double total = 0.0;
        for (std::size_t j = 0; j < normalized.size(); ++j) {
            total += vector_similarity(normalized[i], normalized[j]);
        }
        const float score = static_cast<float>(total / std::max<std::size_t>(1, normalized.size()));
        if (score > best_score) {
            best_score = score;
            best_index = static_cast<int>(i);
        }
    }
    return best_index;
}

std::string float_array_json(const std::vector<float>& values) {
    std::ostringstream out;
    out << "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i) {
            out << ",";
        }
        out << values[i];
    }
    out << "]";
    return out.str();
}

bool assign_recognition_embeddings(const TensorData& embeddings, std::vector<FaceCandidate>* faces, std::string* error) {
    const int face_count = static_cast<int>(faces->size());
    if (face_count <= 0) {
        return true;
    }

    int rows = tensor_rows(embeddings);
    int cols = tensor_cols(embeddings);
    if (rows == face_count && cols > 0) {
        /* expected batched shape */
    } else if (embeddings.values.size() % static_cast<std::size_t>(face_count) == 0) {
        rows = face_count;
        cols = static_cast<int>(embeddings.values.size() / static_cast<std::size_t>(face_count));
    } else {
        std::ostringstream out;
        out << "recognizer output shape does not match face batch: faces=" << face_count
            << " values=" << embeddings.values.size();
        *error = out.str();
        return false;
    }

    if (rows != face_count || cols <= 0 || embeddings.values.size() < static_cast<std::size_t>(rows) * cols) {
        std::ostringstream out;
        out << "recognizer output shape is incomplete: faces=" << face_count
            << " rows=" << rows << " cols=" << cols << " values=" << embeddings.values.size();
        *error = out.str();
        return false;
    }

    for (int i = 0; i < face_count; ++i) {
        FaceCandidate& face = (*faces)[static_cast<std::size_t>(i)];
        const std::size_t start = static_cast<std::size_t>(i) * cols;
        face.embedding.assign(embeddings.values.begin() + start, embeddings.values.begin() + start + cols);
        normalize_vector(&face.embedding);
    }
    return true;
}

std::string faces_json(const std::vector<FaceCandidate>& faces, const Image& image, bool include_embedding) {
    std::ostringstream out;
    out << "[";
    for (std::size_t i = 0; i < faces.size(); ++i) {
        if (i) {
            out << ",";
        }
        const FaceCandidate& face = faces[i];
        out << "{\"confidence\":" << face.score
            << ",\"box\":{\"x\":" << (face.x1 / image.width)
            << ",\"y\":" << (face.y1 / image.height)
            << ",\"width\":" << ((face.x2 - face.x1) / image.width)
            << ",\"height\":" << ((face.y2 - face.y1) / image.height)
            << ",\"unit\":\"normalized\"},\"bbox\":{\"x1\":" << (face.x1 / image.width)
            << ",\"y1\":" << (face.y1 / image.height)
            << ",\"x2\":" << (face.x2 / image.width)
            << ",\"y2\":" << (face.y2 / image.height) << "}";
        out << ",\"landmarks\":[";
        for (int p = 0; p < 5; ++p) {
            if (p) {
                out << ",";
            }
            out << "{\"x\":" << (face.landmarks[p * 2] / image.width)
                << ",\"y\":" << (face.landmarks[p * 2 + 1] / image.height)
                << ",\"unit\":\"normalized\"}";
        }
        out << "]";
        if (include_embedding) {
            out << ",\"embedding\":[";
            for (std::size_t j = 0; j < face.embedding.size(); ++j) {
                if (j) {
                    out << ",";
                }
                out << face.embedding[j];
            }
            out << "]";
        }
        out << "}";
    }
    out << "]";
    return out.str();
}

int write_result(const std::string& output, const std::string& job_id, const std::string& type, const std::vector<FaceCandidate>& faces, const Image& image, bool include_embedding, const InferenceTiming& timing) {
    const std::string result =
        "{\n"
        "  \"contract_version\": \"1.0\",\n"
        "  \"job_id\": \"" + json_escape(job_id) + "\",\n"
        "  \"type\": \"" + type + "\",\n"
        "  \"status\": \"completed\",\n"
        "  \"processor\": {\"name\": \"" + kProcessorName + "\", \"version\": \"" + kVersion + "\", \"backend\": \"" + kBackend + "\"},\n"
        "  \"timing_ms\": " + timing_json(timing) + ",\n"
        "  \"result\": {\"faces\": " + faces_json(faces, image, include_embedding) + "}\n"
        "}\n";
    return write_text(output, result) ? 0 : 3;
}

int write_failed_result(const std::string& output, const std::string& job_id, const std::string& type, const std::string& code, const std::string& message) {
    const std::string result =
        "{\n"
        "  \"contract_version\": \"1.0\",\n"
        "  \"job_id\": \"" + json_escape(job_id) + "\",\n"
        "  \"type\": \"" + type + "\",\n"
        "  \"status\": \"failed\",\n"
        "  \"processor\": {\"name\": \"" + kProcessorName + "\", \"version\": \"" + kVersion + "\", \"backend\": \"" + kBackend + "\"},\n"
        "  \"result\": {\"faces\": []},\n"
        "  \"error\": {\"code\": \"" + json_escape(code) + "\", \"message\": \"" + json_escape(message) + "\", \"retryable\": false, \"phase\": \"inference\"}\n"
        "}\n";
    return write_text(output, result) ? 1 : 3;
}

int write_rank_result(const std::string& payload, const std::string& output) {
    const std::string job_id = extract_string_after(payload, "job_id").empty() ? "local" : extract_string_after(payload, "job_id");
    std::vector<std::vector<float> > targets = extract_float_matrix_after(payload, "target_embeddings");
    std::vector<std::vector<float> > profiles = extract_float_matrix_after(payload, "profile_embeddings");
    if (targets.empty() || profiles.empty()) {
        return write_failed_result(output, job_id, "face_native_rank_embeddings", "invalid_job", "target_embeddings and profile_embeddings are required");
    }
    for (std::size_t i = 0; i < targets.size(); ++i) {
        normalize_vector(&targets[i]);
    }
    for (std::size_t i = 0; i < profiles.size(); ++i) {
        normalize_vector(&profiles[i]);
    }
    std::ostringstream ranks;
    ranks << "[";
    for (std::size_t target_index = 0; target_index < targets.size(); ++target_index) {
        int best_index = -1;
        int second_index = -1;
        float best_score = -std::numeric_limits<float>::infinity();
        float second_score = -std::numeric_limits<float>::infinity();
        for (std::size_t profile_index = 0; profile_index < profiles.size(); ++profile_index) {
            const float score = vector_similarity(targets[target_index], profiles[profile_index]);
            if (score > best_score) {
                second_score = best_score;
                second_index = best_index;
                best_score = score;
                best_index = static_cast<int>(profile_index);
            } else if (score > second_score) {
                second_score = score;
                second_index = static_cast<int>(profile_index);
            }
        }
        if (target_index) {
            ranks << ",";
        }
        if (second_index < 0) {
            second_score = 0.0f;
        }
        ranks << "{\"target_index\":" << target_index
              << ",\"best_index\":" << best_index
              << ",\"best_score\":" << best_score
              << ",\"second_index\":" << second_index
              << ",\"second_score\":" << second_score
              << ",\"margin\":" << (best_score - second_score)
              << "}";
    }
    ranks << "]";
    const std::string result =
        "{\n"
        "  \"contract_version\": \"1.0\",\n"
        "  \"job_id\": \"" + json_escape(job_id) + "\",\n"
        "  \"type\": \"face_native_rank_embeddings\",\n"
        "  \"status\": \"completed\",\n"
        "  \"processor\": {\"name\": \"" + kProcessorName + "\", \"version\": \"" + kVersion + "\", \"backend\": \"" + kBackend + "\"},\n"
        "  \"result\": {\"ranks\": " + ranks.str() + "}\n"
        "}\n";
    return write_text(output, result) ? 0 : 3;
}

int write_profile_math_result(const std::string& payload, const std::string& output) {
    const std::string job_id = extract_string_after(payload, "job_id").empty() ? "local" : extract_string_after(payload, "job_id");
    std::vector<std::vector<float> > embeddings = extract_float_matrix_after(payload, "embeddings");
    if (embeddings.empty()) {
        return write_failed_result(output, job_id, "face_native_profile_math", "invalid_job", "embeddings are required");
    }
    std::vector<float> centroid = centroid_vector(embeddings);
    const int medoid = medoid_index(embeddings);
    double intra = 0.0;
    if (!centroid.empty()) {
        for (std::size_t i = 0; i < embeddings.size(); ++i) {
            std::vector<float> current = embeddings[i];
            normalize_vector(&current);
            intra += vector_similarity(current, centroid);
        }
        intra /= std::max<std::size_t>(1, embeddings.size());
    }
    const std::string result =
        "{\n"
        "  \"contract_version\": \"1.0\",\n"
        "  \"job_id\": \"" + json_escape(job_id) + "\",\n"
        "  \"type\": \"face_native_profile_math\",\n"
        "  \"status\": \"completed\",\n"
        "  \"processor\": {\"name\": \"" + kProcessorName + "\", \"version\": \"" + kVersion + "\", \"backend\": \"" + kBackend + "\"},\n"
        "  \"result\": {\"centroid_embedding\": " + float_array_json(centroid) + ", \"medoid_index\": " + std::to_string(medoid) + ", \"intra_person_similarity\": " + std::to_string(intra) + "}\n"
        "}\n";
    return write_text(output, result) ? 0 : 3;
}

bool setup_ort(OrtHandles* ort, std::string* error) {
    OrtStatus* status = ort->api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "av-imgdata-face-processor", &ort->env);
    if (status) {
        *error = status_message(ort->api, status);
        return false;
    }
    status = ort->api->CreateSessionOptions(&ort->options);
    if (status) {
        *error = status_message(ort->api, status);
        return false;
    }
    const int intra_threads = configured_ort_intra_threads();
    if (intra_threads > 0) {
        status = ort->api->SetIntraOpNumThreads(ort->options, intra_threads);
        if (status) {
            *error = status_message(ort->api, status);
            return false;
        }
    }
    status = ort->api->SetSessionGraphOptimizationLevel(ort->options, configured_ort_graph_level());
    if (status) {
        *error = status_message(ort->api, status);
        return false;
    }
    return true;
}

struct LoadedModels {
    OrtHandles ort;
    OnnxSession detector;
    OnnxSession recognizer;
    bool ort_ready;
    bool detector_ready;
    bool recognizer_ready;
    int recognizer_batch_mode;
    std::string model_root;
    std::string model_name;

    LoadedModels() : ort_ready(false), detector_ready(false), recognizer_ready(false), recognizer_batch_mode(0) {}
};

bool load_models(LoadedModels* models, const std::string& model_root, const std::string& model_name, bool need_recognizer, std::string* error) {
    if (models->detector_ready && models->model_root == model_root && models->model_name == model_name
            && (!need_recognizer || models->recognizer_ready)) {
        return true;
    }
    if (models->detector_ready && (models->model_root != model_root || models->model_name != model_name)) {
        *error = "persistent worker model changes are not supported in one process";
        return false;
    }
    const ModelPaths paths = resolve_models(model_root, model_name);
    if (!file_exists(paths.detector)) {
        *error = "detector model missing: " + paths.detector;
        return false;
    }
    if (need_recognizer && !file_exists(paths.recognizer)) {
        *error = "recognizer model missing: " + paths.recognizer;
        return false;
    }
    if (!models->ort_ready) {
        if (!setup_ort(&models->ort, error)) {
            return false;
        }
        models->ort_ready = true;
    }
    if (!models->detector_ready) {
        if (!load_session(models->ort, paths.detector, &models->detector, error)) {
            *error = "detector session failed: " + *error;
            return false;
        }
        models->detector_ready = true;
        models->model_root = model_root;
        models->model_name = model_name;
    }
    if (need_recognizer && !models->recognizer_ready) {
        if (!load_session(models->ort, paths.recognizer, &models->recognizer, error)) {
            *error = "recognizer session failed: " + *error;
            return false;
        }
        models->recognizer_ready = true;
    }
    return true;
}

int run_inference_payload(const std::string& payload, const std::string& output, const std::string& command, LoadedModels* models) {
    const Clock::time_point total_started = Clock::now();
    InferenceTiming timing;
    const std::string job_id = extract_string_after(payload, "job_id").empty() ? "local" : extract_string_after(payload, "job_id");
    const std::string type = command == "embed" ? "face_native_embed" : "face_native_detect";
    const std::string image_path = extract_string_after(payload, "image_path");
    const std::string model_root = extract_string_after(payload, "model_root");
    const std::string model_name = extract_string_after(payload, "model_name");
    const float min_score = static_cast<float>(extract_number_after(payload, "min_confidence", 0.5));
    const int max_faces = extract_int_after(payload, "max_faces", 0);
    const int det_size = std::max(32, extract_int_after(payload, "det_size", 640));
    if (image_path.empty() || model_root.empty() || model_name.empty()) {
        return write_failed_result(output, job_id, type, "invalid_job", "image_path, model_root and model_name are required");
    }

    Image image;
    std::string error;
    Clock::time_point phase_started = Clock::now();
    if (!decode_image(image_path, &image, &error)) {
        return write_failed_result(output, job_id, type, "image_decode_failed", error);
    }
    timing.image_decode_ms = elapsed_ms(phase_started);
    LoadedModels local_models;
    LoadedModels* active_models = models ? models : &local_models;
    timing.reused_models = active_models->detector_ready && active_models->model_root == model_root
        && active_models->model_name == model_name
        && (command != "embed" || active_models->recognizer_ready);
    phase_started = Clock::now();
    if (!load_models(active_models, model_root, model_name, command == "embed", &error)) {
        const std::string code = error.find("missing:") != std::string::npos ? "model_missing" : "onnxruntime_setup_failed";
        return write_failed_result(output, job_id, type, code, error);
    }
    timing.model_load_ms = elapsed_ms(phase_started);
    phase_started = Clock::now();
    const PreparedImage prepared = prepare_detector_input(image, det_size, det_size);
    timing.detector_prepare_ms = elapsed_ms(phase_started);
    std::vector<TensorData> detector_outputs;
    std::vector<int64_t> detector_shape;
    detector_shape.push_back(1);
    detector_shape.push_back(3);
    detector_shape.push_back(det_size);
    detector_shape.push_back(det_size);
    phase_started = Clock::now();
    if (!run_session(active_models->detector, prepared.nchw, detector_shape, &detector_outputs, &error)) {
        return write_failed_result(output, job_id, type, "detector_run_failed", error);
    }
    timing.detector_run_ms = elapsed_ms(phase_started);
    phase_started = Clock::now();
    std::vector<FaceCandidate> faces = decode_scrfd(detector_outputs, prepared, image, min_score, max_faces);
    timing.detector_decode_ms = elapsed_ms(phase_started);
    if (command == "embed" && !faces.empty()) {
        bool embeddings_ready = false;
        if (faces.size() > 1 && active_models->recognizer_batch_mode >= 0) {
            timing.recognizer_batch_size = static_cast<int>(faces.size());
            std::vector<int64_t> recognizer_shape;
            recognizer_shape.push_back(static_cast<int64_t>(faces.size()));
            recognizer_shape.push_back(3);
            recognizer_shape.push_back(112);
            recognizer_shape.push_back(112);
            phase_started = Clock::now();
            std::vector<float> recog_input = prepare_recognition_batch_input(image, faces);
            timing.recognizer_prepare_ms += elapsed_ms(phase_started);
            std::vector<TensorData> recog_outputs;
            phase_started = Clock::now();
            const bool batch_run_ok = run_session(active_models->recognizer, recog_input, recognizer_shape, &recog_outputs, &error);
            timing.recognizer_run_ms += elapsed_ms(phase_started);
            if (!batch_run_ok) {
                active_models->recognizer_batch_mode = -1;
                timing.recognizer_batch_fallback = true;
            } else if (recog_outputs.empty()) {
                active_models->recognizer_batch_mode = -1;
                timing.recognizer_batch_fallback = true;
            } else {
                timing.recognizer_runs += 1;
                timing.recognizer_batched = true;
                phase_started = Clock::now();
                if (!assign_recognition_embeddings(recog_outputs[0], &faces, &error)) {
                    active_models->recognizer_batch_mode = -1;
                    timing.recognizer_batch_fallback = true;
                } else {
                    active_models->recognizer_batch_mode = 1;
                    timing.recognized_faces = static_cast<int>(faces.size());
                    embeddings_ready = true;
                }
                timing.embedding_normalize_ms += elapsed_ms(phase_started);
            }
        }
        if (!embeddings_ready) {
            std::vector<int64_t> recognizer_shape;
            recognizer_shape.push_back(1);
            recognizer_shape.push_back(3);
            recognizer_shape.push_back(112);
            recognizer_shape.push_back(112);
            for (std::size_t i = 0; i < faces.size(); ++i) {
                phase_started = Clock::now();
                std::vector<float> recog_input = prepare_recognition_input(image, faces[i]);
                timing.recognizer_prepare_ms += elapsed_ms(phase_started);
                std::vector<TensorData> recog_outputs;
                phase_started = Clock::now();
                if (!run_session(active_models->recognizer, recog_input, recognizer_shape, &recog_outputs, &error)) {
                    return write_failed_result(output, job_id, type, "recognizer_run_failed", error);
                }
                timing.recognizer_run_ms += elapsed_ms(phase_started);
                timing.recognizer_runs += 1;
                if (!recog_outputs.empty()) {
                    faces[i].embedding = recog_outputs[0].values;
                    phase_started = Clock::now();
                    normalize_vector(&faces[i].embedding);
                    timing.embedding_normalize_ms += elapsed_ms(phase_started);
                    timing.recognized_faces += 1;
                }
            }
            if (timing.recognizer_batch_size == 0) {
                timing.recognizer_batch_size = faces.size() > 1 ? 1 : static_cast<int>(faces.size());
            }
        }
    }
    timing.total_ms = elapsed_ms(total_started);
    return write_result(output, job_id, type, faces, image, command == "embed", timing);
}

std::string extract_faces_json(const std::string& payload) {
    return extract_array_after(payload, "faces").empty() ? "[]" : extract_array_after(payload, "faces");
}

int run_batch_inference_payload(const std::string& payload, const std::string& output, const std::string& command, LoadedModels* models) {
    const Clock::time_point total_started = Clock::now();
    const std::string job_id = extract_string_after(payload, "job_id").empty() ? "local" : extract_string_after(payload, "job_id");
    const std::string type = command == "embed_batch" ? "face_native_embed_batch" : "face_native_detect_batch";
    std::vector<std::string> image_paths = extract_string_array_after(payload, "image_paths");
    if (image_paths.empty()) {
        const std::string image_path = extract_string_after(payload, "image_path");
        if (!image_path.empty()) {
            image_paths.push_back(image_path);
        }
    }
    const std::string model_root = extract_string_after(payload, "model_root");
    const std::string model_name = extract_string_after(payload, "model_name");
    const float min_score = static_cast<float>(extract_number_after(payload, "min_confidence", 0.5));
    const int max_faces = extract_int_after(payload, "max_faces", 0);
    const int det_size = std::max(32, extract_int_after(payload, "det_size", 640));
    if (image_paths.empty() || model_root.empty() || model_name.empty()) {
        return write_failed_result(output, job_id, type, "invalid_job", "image_paths, model_root and model_name are required");
    }
    std::ostringstream images;
    images << "[";
    int failed_count = 0;
    for (std::size_t i = 0; i < image_paths.size(); ++i) {
        const std::string item_output = output + "." + std::to_string(i) + ".json";
        std::ostringstream item_payload;
        item_payload << "{"
                     << "\"contract_version\":\"1.0\","
                     << "\"job_id\":\"" << json_escape(job_id) << "-" << i << "\","
                     << "\"type\":\"face_native_" << (command == "embed_batch" ? "embed" : "detect") << "\","
                     << "\"input\":{\"image_path\":\"" << json_escape(image_paths[i]) << "\",\"source_id\":\"" << json_escape(image_paths[i]) << "\"},"
                     << "\"options\":{\"model_root\":\"" << json_escape(model_root) << "\",\"model_name\":\"" << json_escape(model_name)
                     << "\",\"min_confidence\":" << min_score << ",\"max_faces\":" << max_faces
                     << ",\"det_size\":[" << det_size << "," << det_size << "],\"normalize_coordinates\":true}"
                     << "}";
        const int returncode = run_inference_payload(item_payload.str(), item_output, command == "embed_batch" ? "embed" : "detect", models);
        const std::string item_result = read_text(item_output);
        const bool completed = returncode == 0 && item_result.find("\"status\": \"completed\"") != std::string::npos;
        if (!completed) {
            ++failed_count;
        }
        if (i) {
            images << ",";
        }
        images << "{\"image_path\":\"" << json_escape(image_paths[i])
               << "\",\"source_id\":\"" << json_escape(image_paths[i])
               << "\",\"status\":\"" << (completed ? "completed" : "failed")
               << "\",\"faces\":" << extract_faces_json(item_result)
               << "}";
        unlink(item_output.c_str());
    }
    images << "]";
    const std::string result =
        "{\n"
        "  \"contract_version\": \"1.0\",\n"
        "  \"job_id\": \"" + json_escape(job_id) + "\",\n"
        "  \"type\": \"" + type + "\",\n"
        "  \"status\": \"" + std::string(failed_count == static_cast<int>(image_paths.size()) ? "failed" : "completed") + "\",\n"
        "  \"processor\": {\"name\": \"" + kProcessorName + "\", \"version\": \"" + kVersion + "\", \"backend\": \"" + kBackend + "\"},\n"
        "  \"timing_ms\": {\"total\": " + std::to_string(elapsed_ms(total_started)) + ", \"batch_size\": " + std::to_string(image_paths.size()) + ", \"failed_images\": " + std::to_string(failed_count) + "},\n"
        "  \"result\": {\"images\": " + images.str() + "}\n"
        "}\n";
    if (!write_text(output, result)) {
        return 3;
    }
    return failed_count == static_cast<int>(image_paths.size()) ? 1 : 0;
}

int run_inference_job(const std::vector<std::string>& args, const std::string& command) {
    const std::string input = arg_value(args, "--input");
    const std::string output = arg_value(args, "--output");
    if (input.empty() || output.empty()) {
        std::cerr << "--input and --output are required\n";
        return 2;
    }
    const std::string payload = read_text(input);
    if (command == "embed_batch" || command == "detect_batch") {
        return run_batch_inference_payload(payload, output, command, NULL);
    }
    if (command == "rank_embeddings") {
        return write_rank_result(payload, output);
    }
    if (command == "profile_math") {
        return write_profile_math_result(payload, output);
    }
    return run_inference_payload(payload, output, command, NULL);
}

int run_worker() {
    LoadedModels models;
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) {
            continue;
        }
        const std::string request_id = extract_string_after(line, "request_id");
        const std::string command = extract_string_after(line, "command");
        const std::string input = extract_string_after(line, "input");
        const std::string output = extract_string_after(line, "output");
        int returncode = 2;
        if ((command == "detect" || command == "embed") && !input.empty() && !output.empty()) {
            returncode = run_inference_payload(read_text(input), output, command, &models);
        } else if ((command == "detect_batch" || command == "embed_batch") && !input.empty() && !output.empty()) {
            returncode = run_batch_inference_payload(read_text(input), output, command, &models);
        } else if (command == "rank_embeddings" && !input.empty() && !output.empty()) {
            returncode = write_rank_result(read_text(input), output);
        } else if (command == "profile_math" && !input.empty() && !output.empty()) {
            returncode = write_profile_math_result(read_text(input), output);
        }
        std::cout << "{\"request_id\":\"" << json_escape(request_id)
                  << "\",\"returncode\":" << returncode << "}" << std::endl;
    }
    return 0;
}

int probe_models(const std::string& model_root, const std::string& model_name) {
    if (model_root.empty() || model_name.empty()) {
        std::cerr << "model root and model name are required\n";
        return 4;
    }
    const ModelPaths paths = resolve_models(model_root, model_name);
    if (!file_exists(paths.detector)) {
        std::cerr << "detector model missing: " << paths.detector << "\n";
        return 4;
    }
    if (!file_exists(paths.recognizer)) {
        std::cerr << "recognizer model missing: " << paths.recognizer << "\n";
        return 4;
    }

    OrtHandles ort;
    std::string error;
    if (!setup_ort(&ort, &error)) {
        std::cerr << error << "\n";
        return 4;
    }

    if (!create_session(ort, paths.detector, &error)) {
        std::cerr << "detector session failed: " << error << "\n";
        return 4;
    }
    if (!create_session(ort, paths.recognizer, &error)) {
        std::cerr << "recognizer session failed: " << error << "\n";
        return 4;
    }
    std::string heif_reason;
    const bool heif_available = heif_decoder_available(&heif_reason);
    std::cout << "probe accepted by " << kBackend << " for " << model_root << "/" << model_name
              << " ort_intra_threads=" << configured_ort_intra_threads()
              << " ort_graph_opt=" << configured_ort_graph_level_name()
              << " heif_decoder=" << (heif_available ? "available" : "unavailable");
    if (!heif_available) {
        std::cout << " heif_reason=\"" << heif_reason << "\"";
    }
    std::cout << "\n";
    return 0;
}

int write_unimplemented_result(const std::vector<std::string>& args, const std::string& command) {
    const std::string input = arg_value(args, "--input");
    const std::string output = arg_value(args, "--output");
    if (input.empty() || output.empty()) {
        std::cerr << "--input and --output are required\n";
        return 2;
    }
    const std::string payload = read_text(input);
    const std::string job_id = extract_string_after(payload, "job_id").empty() ? "local" : extract_string_after(payload, "job_id");
    const std::string type = command == "embed" ? "face_native_embed" : "face_native_detect";
    const std::string result =
        "{\n"
        "  \"contract_version\": \"1.0\",\n"
        "  \"job_id\": \"" + json_escape(job_id) + "\",\n"
        "  \"type\": \"" + type + "\",\n"
        "  \"status\": \"failed\",\n"
        "  \"processor\": {\"name\": \"" + kProcessorName + "\", \"version\": \"" + kVersion + "\", \"backend\": \"" + kBackend + "\"},\n"
        "  \"result\": {\"faces\": []},\n"
        "  \"error\": {\"code\": \"native_inference_not_complete\", \"message\": \"ONNXRuntime sessions are available, but SCRFD/ArcFace preprocessing and postprocessing are not implemented yet\", \"retryable\": false, \"phase\": \"inference\"}\n"
        "}\n";
    if (!write_text(output, result)) {
        std::cerr << "could not write result: " << output << "\n";
        return 3;
    }
    return 1;
}

int run_onnxruntime_backend(int argc, char** argv) {
    std::vector<std::string> args;
    for (int i = 1; i < argc; ++i) {
        args.push_back(argv[i]);
    }
    if (args.empty()) {
        std::cerr << "usage: av-imgdata-face-processor <version|probe|detect|embed|detect_batch|embed_batch|rank_embeddings|profile_math|worker|self-test>\n";
        return 2;
    }

    const std::string command = args[0];
    if (command == "version") {
        std::cout << kProcessorName << " " << kVersion << "\n";
        return 0;
    }
    if (command == "probe" || command == "self-test") {
        return probe_models(arg_value(args, "--model-root"), arg_value(args, "--model-name"));
    }
    if (command == "worker") {
        return run_worker();
    }
    if (
            command == "detect" || command == "embed"
            || command == "detect_batch" || command == "embed_batch"
            || command == "rank_embeddings" || command == "profile_math") {
        return run_inference_job(args, command);
    }
    std::cerr << "unknown command: " << command << "\n";
    return 2;
}

}  // namespace

int main(int argc, char** argv) {
    return run_onnxruntime_backend(argc, argv);
}
