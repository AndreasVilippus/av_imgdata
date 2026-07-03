#include "av_imgdata_image/cli.h"
#include <iostream>
#include <algorithm>

namespace av_imgdata {
namespace image {

CommandLineArgs CLI::parse_args(int argc, char* argv[]) {
  CommandLineArgs args;
  
  if (argc < 2) {
    return args;
  }
  
  // First argument is the command
  args.operation = get_operation(argv[1]);
  
  // Parse remaining arguments
  for (int i = 2; i < argc; ++i) {
    std::string arg = argv[i];
    
    if (arg == "--input" || arg == "-i") {
      if (auto val = get_arg_value(std::vector<std::string>(argv + 2, argv + argc), i, arg)) {
        args.input_file = val.value();
      }
    } else if (arg == "--output" || arg == "-o") {
      if (auto val = get_arg_value(std::vector<std::string>(argv + 2, argv + argc), i, arg)) {
        args.output_file = val.value();
      }
    } else if (arg == "--workdir" || arg == "-w") {
      if (auto val = get_arg_value(std::vector<std::string>(argv + 2, argv + argc), i, arg)) {
        args.workdir = val.value();
      }
    } else {
      args.extra_args.push_back(arg);
    }
  }
  
  return args;
}

Operation CLI::get_operation(const std::string& cmd) {
  std::string lower_cmd = cmd;
  std::transform(lower_cmd.begin(), lower_cmd.end(), lower_cmd.begin(), ::tolower);
  
  if (lower_cmd == "version") return Operation::VERSION;
  if (lower_cmd == "probe") return Operation::PROBE;
  if (lower_cmd == "info") return Operation::INFO;
  if (lower_cmd == "process") return Operation::PROCESS;
  
  return Operation::UNKNOWN;
}

void CLI::print_usage(const char* program_name) {
  std::cerr << "Usage: " << program_name << " <command> [options]\n"
            << "\nCommands:\n"
            << "  version              Print version information\n"
            << "  probe                Probe processor capabilities\n"
            << "  info                 Get image information\n"
            << "  process              Process image\n"
            << "\nOptions:\n"
            << "  --input <file>       Input JSON file or image path\n"
            << "  --output <file>      Output JSON file\n"
            << "  --workdir <dir>      Working directory for temporary files\n"
            << std::endl;
}

void CLI::print_help(Operation op) {
  switch (op) {
    case Operation::VERSION:
      std::cerr << "Print version information of the image processor\n"
                << "Usage: av-imgdata-image-processor version\n";
      break;
    case Operation::PROBE:
      std::cerr << "Probe processor capabilities\n"
                << "Usage: av-imgdata-image-processor probe [--output <file>]\n";
      break;
    case Operation::INFO:
      std::cerr << "Get image information\n"
                << "Usage: av-imgdata-image-processor info --input <file> --output <file>\n";
      break;
    case Operation::PROCESS:
      std::cerr << "Process image with specified operation\n"
                << "Usage: av-imgdata-image-processor process --input <json> --output <json> --workdir <dir>\n";
      break;
    default:
      std::cerr << "Unknown command\n";
  }
}

std::optional<std::string> CLI::get_arg_value(
  const std::vector<std::string>& args,
  int& idx,
  const std::string& flag) {
  
  // Find the flag in the args
  for (size_t i = 0; i < args.size(); ++i) {
    if (args[i] == flag || args[i] == "-" + flag.substr(flag.find_last_of('-') + 1)) {
      if (i + 1 < args.size()) {
        return args[i + 1];
      }
    }
  }
  return std::nullopt;
}

} // namespace image
} // namespace av_imgdata
