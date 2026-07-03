#pragma once

#include <string>
#include <nlohmann/json.hpp>
#include "types.h"

namespace av_imgdata {
namespace image {

using json = nlohmann::json;

class JsonIO {
public:
  // Parse job input from JSON file
  static JobInput read_job_input(const std::string& path);
  
  // Write job input to JSON file
  static void write_job_input(const std::string& path, const JobInput& input);
  
  // Parse job input from JSON string
  static JobInput parse_job_input(const std::string& json_str);
  
  // Convert job input to JSON
  static json job_input_to_json(const JobInput& input);
  
  // Write process result to JSON file
  static void write_process_result(const std::string& path, const ProcessResult& result);
  
  // Convert process result to JSON
  static json process_result_to_json(const ProcessResult& result);
  
  // Write probe result to JSON file
  static void write_probe_result(const std::string& path, const ProbeResult& result);
  
  // Convert probe result to JSON
  static json probe_result_to_json(const ProbeResult& result);

private:
  static void validate_json(const json& data, const std::string& field);
};

} // namespace image
} // namespace av_imgdata
