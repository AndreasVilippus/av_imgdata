cmake_minimum_required(VERSION 3.16)
project(av_imgdata_image_processor LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Version information
set(PROJECT_VERSION_MAJOR 0)
set(PROJECT_VERSION_MINOR 2)
set(PROJECT_VERSION_PATCH 0)
set(PROJECT_VERSION "${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}.${PROJECT_VERSION_PATCH}")

# Options
option(AV_IMGDATA_ENABLE_VIPS "Enable libvips backend" ON)
option(AV_IMGDATA_ENABLE_PNG "Enable PNG decoding" OFF)
option(AV_IMGDATA_ENABLE_TIFF "Enable TIFF decoding" OFF)

# Source files
set(SOURCES
  src/main.cpp
  src/cli.cpp
  src/json_io.cpp
  src/image_loader.cpp
  src/image_processor.cpp
  src/result_writer.cpp
  src/errors.cpp
)

# Headers
set(HEADERS
  include/av_imgdata_image/cli.h
  include/av_imgdata_image/json_io.h
  include/av_imgdata_image/image_loader.h
  include/av_imgdata_image/image_processor.h
  include/av_imgdata_image/result_writer.h
  include/av_imgdata_image/errors.h
  include/av_imgdata_image/types.h
)

# Add executable
add_executable(av-imgdata-image-processor ${SOURCES} ${HEADERS})

# Include directories
target_include_directories(av-imgdata-image-processor PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Find required packages
find_package(PkgConfig REQUIRED)

# Find libvips
if(AV_IMGDATA_ENABLE_VIPS)
  pkg_check_modules(VIPS REQUIRED IMPORTED_TARGET vips)
  target_link_libraries(av-imgdata-image-processor PRIVATE PkgConfig::VIPS)
  target_compile_definitions(av-imgdata-image-processor PRIVATE ENABLE_VIPS=1)
else()
  message(STATUS "Building libvips image processor skeleton (vips disabled)")
  target_compile_definitions(av-imgdata-image-processor PRIVATE ENABLE_VIPS=0)
endif()

# Find libjpeg-turbo
pkg_check_modules(JPEG REQUIRED IMPORTED_TARGET libjpeg)
target_link_libraries(av-imgdata-image-processor PRIVATE PkgConfig::JPEG)

# Optional: Find libpng
if(AV_IMGDATA_ENABLE_PNG)
  pkg_check_modules(PNG REQUIRED IMPORTED_TARGET libpng)
  target_link_libraries(av-imgdata-image-processor PRIVATE PkgConfig::PNG)
  target_compile_definitions(av-imgdata-image-processor PRIVATE ENABLE_PNG=1)
endif()

# Optional: Find libtiff
if(AV_IMGDATA_ENABLE_TIFF)
  pkg_check_modules(TIFF REQUIRED IMPORTED_TARGET libtiff-4)
  target_link_libraries(av-imgdata-image-processor PRIVATE PkgConfig::TIFF)
  target_compile_definitions(av-imgdata-image-processor PRIVATE ENABLE_TIFF=1)
endif()

# Compiler flags
if(MSVC)
  target_compile_options(av-imgdata-image-processor PRIVATE /W4)
else()
  target_compile_options(av-imgdata-image-processor PRIVATE -Wall -Wextra -Wpedantic)
  # Set RPATH for runtime library lookup
  target_link_options(av-imgdata-image-processor PRIVATE "-Wl,-rpath,$ORIGIN/../lib")
endif()

# Installation
install(TARGETS av-imgdata-image-processor RUNTIME DESTINATION bin)

# Print configuration
message(STATUS "=== AV_ImgData Image Processor Configuration ===")
message(STATUS "Version: ${PROJECT_VERSION}")
message(STATUS "libvips: ${AV_IMGDATA_ENABLE_VIPS}")
message(STATUS "PNG support: ${AV_IMGDATA_ENABLE_PNG}")
message(STATUS "TIFF support: ${AV_IMGDATA_ENABLE_TIFF}")
message(STATUS "==============================================")
