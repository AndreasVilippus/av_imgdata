#pragma once

#include <string>
#include <vector>
#include <optional>
#include "types.h"

namespace av_imgdata {
namespace image {

struct CommandLineArgs {
  Operation operation = Operation::UNKNOWN;
  std::string input_file;
  std::string output_file;
  std::string workdir;
  std::vector<std::string> extra_args;
};

class CLI {
public:
  // Parse command line arguments
  static CommandLineArgs parse_args(int argc, char* argv[]);
  
  // Get operation from string
  static Operation get_operation(const std::string& cmd);
  
  // Print usage information
  static void print_usage(const char* program_name);
  
  // Print help for a command
  static void print_help(Operation op);

private:
  static std::optional<std::string> get_arg_value(
    const std::vector<std::string>& args,
    int& idx,
    const std::string& flag
  );
};

} // namespace image
} // namespace av_imgdata
