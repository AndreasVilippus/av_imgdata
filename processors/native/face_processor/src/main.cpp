#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

namespace {

bool is_executable(const std::string& path) {
    return !path.empty() && access(path.c_str(), X_OK) == 0;
}

std::string dirname_of(const std::string& path) {
    const std::string::size_type pos = path.find_last_of('/');
    if (pos == std::string::npos) {
        return ".";
    }
    if (pos == 0) {
        return "/";
    }
    return path.substr(0, pos);
}

std::string package_root(const char* argv0) {
    const char* env = getenv("SYNOPKG_PKGDEST");
    if (env && *env) {
        return std::string(env);
    }

    char resolved[4096];
    ssize_t length = readlink("/proc/self/exe", resolved, sizeof(resolved) - 1);
    if (length > 0) {
        resolved[length] = '\0';
        const std::string bin_dir = dirname_of(std::string(resolved));
        return dirname_of(bin_dir);
    }

    return dirname_of(dirname_of(std::string(argv0 ? argv0 : "")));
}

std::string python_binary(const std::string& root) {
    const char* env = getenv("AV_IMGDATA_PYTHON");
    if (env && *env && is_executable(env)) {
        return std::string(env);
    }

    const std::string package_python = root + "/var/venv/bin/python";
    if (is_executable(package_python)) {
        return package_python;
    }

    const std::string synology_python = "/var/packages/Python3/target/bin/python3";
    if (is_executable(synology_python)) {
        return synology_python;
    }

    return "python3";
}

void extend_pythonpath(const std::string& root) {
    const std::string package_src = root + "/src";
    const char* current = getenv("PYTHONPATH");
    std::string value = package_src;
    if (current && *current) {
        value += ":";
        value += current;
    }
    setenv("PYTHONPATH", value.c_str(), 1);
}

}  // namespace

int main(int argc, char** argv) {
    const std::string root = package_root(argc > 0 ? argv[0] : "");
    extend_pythonpath(root);

    std::vector<std::string> args;
    args.push_back(python_binary(root));
    args.push_back("-m");
    args.push_back("services.native_face_processor_worker");
    for (int i = 1; i < argc; ++i) {
        args.push_back(argv[i]);
    }

    std::vector<char*> exec_args;
    for (std::size_t i = 0; i < args.size(); ++i) {
        exec_args.push_back(const_cast<char*>(args[i].c_str()));
    }
    exec_args.push_back(NULL);

    execvp(exec_args[0], exec_args.data());
    std::cerr << "could not start native face processor worker via " << args[0]
              << ": " << std::strerror(errno) << "\n";
    return 127;
}
