cmake_minimum_required(VERSION 3.16)
project(av_imgdata_worker LANGUAGES CXX)

# Skeleton only.
# The first real target should add av-imgdata-worker with version/probe/once/run commands.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(AV_IMGDATA_WORKER_BUILD_TESTS "Build external worker tests" OFF)
option(AV_IMGDATA_WORKER_BUNDLE_FACE_PROCESSOR "Bundle av-imgdata-face-processor with the worker artifact" ON)
option(AV_IMGDATA_WORKER_BUNDLE_VIPS_PROCESSOR "Bundle av-imgdata-image-processor with the worker artifact" OFF)

# Planned target:
# add_executable(av-imgdata-worker
#   src/main.cpp
#   src/config.cpp
#   src/dsm_client.cpp
#   src/worker_loop.cpp
#   src/processor_runner.cpp
#   src/capabilities.cpp
#   src/workspace.cpp
#   src/result_validator.cpp
# )
#
# target_include_directories(av-imgdata-worker PRIVATE include)
# install(TARGETS av-imgdata-worker RUNTIME DESTINATION bin)
