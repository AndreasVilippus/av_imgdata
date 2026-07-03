#pragma once

#include <string>
#include <vector>
#include <map>
#include <optional>
#include <memory>

namespace av_imgdata {
namespace image {

// Contract version
inline constexpr const char* CONTRACT_VERSION = "1.0";

// Operation types
enum class Operation {
  VERSION,
  PROBE,
  INFO,
  PROCESS,
  UNKNOWN
};

// Image format types
enum class ImageFormat {
  JPEG,
  PNG,
  WEBP,
  TIFF,
  UNKNOWN
};

// Processing operations
enum class ProcessOperation {
  RESIZE,
  ROTATE,
  CONVERT,
  AUTO_ORIENT,
  CUSTOM
};

// Result status
enum class ResultStatus {
  SUCCESS = 0,
  ERROR_INVALID_INPUT = 1,
  ERROR_IMAGE_NOT_FOUND = 2,
  ERROR_UNSUPPORTED_FORMAT = 3,
  ERROR_PROCESSING_FAILED = 4,
  ERROR_OUTPUT_FAILED = 5,
  ERROR_INVALID_JSON = 6,
  ERROR_UNKNOWN = 99
};

// Job input structure
struct JobInput {
  std::string contract_version;
  std::string image_path;
  std::string operation;
  std::string output_format;
  std::map<std::string, std::string> options;
  double timestamp = 0.0;
};

// Processing options
struct ProcessOptions {
  int width = 0;
  int height = 0;
  int angle = 0;
  int quality = 95;
  bool maintain_aspect = true;
  std::string output_format = "jpeg";
};

// Image information
struct ImageInfo {
  int width = 0;
  int height = 0;
  ImageFormat format = ImageFormat::UNKNOWN;
  std::string color_space;
  bool has_alpha = false;
  int orientation = 1; // EXIF orientation
};

// Processing result
struct ProcessResult {
  ResultStatus status = ResultStatus::SUCCESS;
  std::string contract_version = CONTRACT_VERSION;
  std::string operation;
  std::string output_path;
  std::string output_format;
  int width = 0;
  int height = 0;
  double timestamp = 0.0;
  std::map<std::string, std::string> metadata;
  std::optional<std::string> error;
};

// Probe result
struct ProbeResult {
  std::string contract_version = CONTRACT_VERSION;
  std::string backend;
  bool available = false;
  std::string reason;
  std::map<std::string, bool> formats;
  std::optional<std::string> error;
};

} // namespace image
} // namespace av_imgdata
