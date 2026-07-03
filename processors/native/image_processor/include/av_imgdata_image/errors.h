#pragma once

#include <stdexcept>
#include <string>
#include "types.h"

namespace av_imgdata {
namespace image {

// Exception base class
class ImageProcessorException : public std::runtime_error {
public:
  explicit ImageProcessorException(const std::string& message, ResultStatus status = ResultStatus::ERROR_UNKNOWN)
    : std::runtime_error(message), status_(status) {}
  
  ResultStatus status() const { return status_; }

private:
  ResultStatus status_;
};

// Specific exceptions
class ImageNotFoundException : public ImageProcessorException {
public:
  explicit ImageNotFoundException(const std::string& path)
    : ImageProcessorException("Image not found: " + path, ResultStatus::ERROR_IMAGE_NOT_FOUND) {}
};

class UnsupportedFormatException : public ImageProcessorException {
public:
  explicit UnsupportedFormatException(const std::string& format)
    : ImageProcessorException("Unsupported format: " + format, ResultStatus::ERROR_UNSUPPORTED_FORMAT) {}
};

class InvalidJsonException : public ImageProcessorException {
public:
  explicit InvalidJsonException(const std::string& message)
    : ImageProcessorException("Invalid JSON: " + message, ResultStatus::ERROR_INVALID_JSON) {}
};

class ProcessingFailedException : public ImageProcessorException {
public:
  explicit ProcessingFailedException(const std::string& message)
    : ImageProcessorException("Processing failed: " + message, ResultStatus::ERROR_PROCESSING_FAILED) {}
};

class OutputFailedException : public ImageProcessorException {
public:
  explicit OutputFailedException(const std::string& message)
    : ImageProcessorException("Output failed: " + message, ResultStatus::ERROR_OUTPUT_FAILED) {}
};

} // namespace image
} // namespace av_imgdata
