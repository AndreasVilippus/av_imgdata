#include "av_imgdata/worker_protocol.h"
#include "av_imgdata/worker_runtime.h"

#include <cassert>
#include <filesystem>
#include <iostream>
#include <string>

int main() {
    namespace runtime = av_imgdata::worker::runtime;

    assert(std::string(av_imgdata::worker::kProtocolVersion) == "1.0");
    assert(std::string(av_imgdata::worker::kWorkerVersion) == "0.10.0");
    assert(av_imgdata::worker::kCapabilities.size() == 7);
    assert(av_imgdata::worker::kInputModes.size() == 1);
    assert(av_imgdata::worker::capabilities_json().find("face_native_embed") != std::string::npos);
    assert(av_imgdata::worker::input_modes_json() == "[\"shared_path\"]");

    const std::string json = R"({"worker_id":"worker-01","poll_interval_seconds":5,"values":[1,2],"nested":{"name":"x"}})";
    assert(runtime::extract_json_string(json, "worker_id") == "worker-01");
    assert(runtime::extract_json_scalar(json, "poll_interval_seconds", "2") == "5");
    assert(runtime::extract_json_array(json, "values") == "[1,2]");
    assert(runtime::extract_json_string(runtime::extract_json_object(json, "nested"), "name") == "x");

    std::string normalized;
    std::string error;
    assert(runtime::safe_relative_path("folder/image.jpg", &normalized, &error));
    assert(normalized == "folder/image.jpg");
    assert(!runtime::safe_relative_path("../escape.jpg", &normalized, &error));
    assert(error == "local_path_escape");
    assert(!runtime::safe_relative_path("/absolute.jpg", &normalized, &error));
    assert(error == "local_path_must_be_relative");

    const auto command = runtime::build_process_command(
        "C:\\Program Files\\AV ImgData\\processor.exe",
        {"version"}
    );
#ifdef _WIN32
    assert(command.find("cmd.exe /D /S /C \"\"C:\\Program Files\\AV ImgData\\processor.exe\"") == 0);
    assert(command.find("\"version\" 2>&1\"") != std::string::npos);
#else
    assert(command.find("'C:\\Program Files\\AV ImgData\\processor.exe' 'version' 2>&1") == 0);
#endif

    const auto temp = std::filesystem::temp_directory_path() / "av-imgdata-worker-runtime-test";
    std::error_code ec;
    std::filesystem::remove_all(temp, ec);
    const auto file = temp / "nested" / "value.txt";
    assert(runtime::write_file(file.string(), "value"));
    assert(runtime::file_exists(file.string()));
    assert(runtime::read_file(file.string()) == "value");
    std::filesystem::remove_all(temp, ec);

    std::cout << "worker runtime tests passed\n";
    return 0;
}
