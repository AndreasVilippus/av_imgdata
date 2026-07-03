#pragma once

#include <string>
#include "types.h"

namespace av_imgdata {
namespace image {

class ResultWriter {
public:
  // Write process result to file and stdout
  static int write_process_result(const ProcessResult& result, const std::string& output_file);
  
  // Write probe result to file and stdout
  static int write_probe_result(const ProbeResult& result, const std::string& output_file);
  
  // Write version string to stdout
  static void write_version();
  
  // Format result as JSON string
  static std::string format_process_result(const ProcessResult& result);
  static std::string format_probe_result(const ProbeResult& result);

private:
  static std::string status_to_string(ResultStatus status);
};

} // namespace image
} // namespace av_imgdata
