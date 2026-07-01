cmake_minimum_required(VERSION 3.10)
project(av_imgdata_face_processor LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(av-imgdata-face-processor src/main.cpp)

install(TARGETS av-imgdata-face-processor RUNTIME DESTINATION bin)
