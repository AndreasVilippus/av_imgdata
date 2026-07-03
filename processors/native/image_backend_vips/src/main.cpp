#include <iostream>
#include <string>

namespace {

void print_usage() {
    std::cout
        << "av-imgdata-image-processor commands: version, probe, image-info, thumbnail, normalize-for-face, self-test\n";
}

int print_probe() {
    std::cout
        << "{"
        << "\"contract_version\":\"1.0\","
        << "\"processor\":{\"name\":\"av-imgdata-image-processor\",\"backend\":\"skeleton\",\"version\":\"0.1.0-skeleton\"},"
        << "\"backend\":\"skeleton\","
        << "\"available\":false,"
        << "\"reason\":\"vips_probe_failed\","
        << "\"formats\":{\"jpeg\":false,\"jpg\":false,\"png\":false,\"webp\":false,\"tiff\":false,\"heic\":false,\"heif\":false},"
        << "\"error\":{\"code\":\"libvips_not_linked\",\"message\":\"libvips image backend is not built into this skeleton binary\"}"
        << "}\n";
    return 1;
}

} // namespace

int main(int argc, char** argv) {
    const std::string command = argc > 1 ? std::string(argv[1]) : "";
    if (command == "version") {
        std::cout << "av-imgdata-image-processor 0.1.0-skeleton image-backend-vips\n";
        return 0;
    }
    if (command == "probe") {
        return print_probe();
    }
    if (command == "image-info" || command == "thumbnail" || command == "normalize-for-face" || command == "self-test") {
        std::cerr << "libvips image backend is not built into this skeleton binary\n";
        return 1;
    }
    print_usage();
    return command.empty() ? 1 : 2;
}
