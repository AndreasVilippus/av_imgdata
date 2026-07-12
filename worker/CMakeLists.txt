cmake_minimum_required(VERSION 3.16)
project(av_imgdata_worker LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(AV_IMGDATA_WORKER_VERSION "0.10.0" CACHE STRING "External worker bundle version")

option(AV_IMGDATA_WORKER_BUILD_TESTS "Build external worker tests" OFF)
option(AV_IMGDATA_WORKER_BUNDLE_FACE_PROCESSOR "Bundle av-imgdata-face-processor with the worker artifact" ON)
option(AV_IMGDATA_WORKER_BUNDLE_VIPS_PROCESSOR "Bundle av-imgdata-image-processor with the worker artifact" OFF)

add_library(av-imgdata-worker-runtime INTERFACE)
target_include_directories(av-imgdata-worker-runtime INTERFACE include)
target_compile_definitions(av-imgdata-worker-runtime INTERFACE
  AV_IMGDATA_WORKER_VERSION="${AV_IMGDATA_WORKER_VERSION}"
)

add_executable(av-imgdata-worker
  src/main.cpp
)

add_executable(av-imgdata-worker-api-loop
  src/api_loop.cpp
)

target_link_libraries(av-imgdata-worker PRIVATE av-imgdata-worker-runtime)
target_link_libraries(av-imgdata-worker-api-loop PRIVATE av-imgdata-worker-runtime)

if(MINGW)
  target_link_options(av-imgdata-worker PRIVATE
    -static-libgcc
    -static-libstdc++
  )
  target_link_options(av-imgdata-worker-api-loop PRIVATE
    -static-libgcc
    -static-libstdc++
  )
endif()

install(TARGETS av-imgdata-worker av-imgdata-worker-api-loop RUNTIME DESTINATION bin)
install(FILES config/worker-config.example.json DESTINATION config)
install(FILES config/worker-config.schema.json DESTINATION config)
install(FILES jobs/sample-worker-job.json DESTINATION jobs)

if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/../processor_contract/schemas/face-native-job-input.schema.json")
  install(DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/../processor_contract/schemas" DESTINATION share/processor_contract)
endif()

install(DIRECTORY packaging/ DESTINATION packaging)
if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/packaging/windows/Initialize-AVImgDataWorker.ps1")
  install(FILES packaging/windows/Initialize-AVImgDataWorker.ps1 DESTINATION .)
endif()
