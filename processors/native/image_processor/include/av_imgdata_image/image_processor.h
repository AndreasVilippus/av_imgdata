#pragma once

#include <string>
#include <memory>
#include "types.h"

namespace av_imgdata {
namespace image {

class ImageProcessor {
public:
  // Process image with given operation
  static ProcessResult process_image(const JobInput& input, const std::string& workdir);
  
  // Resize image
  static ProcessResult resize_image(const std::string& input_path, 
                                    const std::string& output_path,
                                    const ProcessOptions& options);
  
  // Rotate image
  static ProcessResult rotate_image(const std::string& input_path,
                                   const std::string& output_path,
                                   int angle);
  
  // Convert image format
  static ProcessResult convert_image(const std::string& input_path,
                                    const std::string& output_path,
                                    const std::string& format,
                                    int quality = 95);
  
  // Auto-orient image based on EXIF
  static ProcessResult auto_orient_image(const std::string& input_path,
                                        const std::string& output_path);

private:
  static int parse_quality(const std::string& quality_str);
};

} // namespace image
} // namespace av_imgdata
