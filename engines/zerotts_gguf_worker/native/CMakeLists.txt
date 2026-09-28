cmake_minimum_required(VERSION 3.16)
project(omni-zerotts-gguf-server CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED ZEROTTS_SOURCE_DIR)
    message(FATAL_ERROR "ZEROTTS_SOURCE_DIR is required")
endif()

set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(GGML_STATIC ON CACHE BOOL "" FORCE)
add_subdirectory("${ZEROTTS_SOURCE_DIR}/cpp" zerotts-upstream)
if(WIN32)
    target_compile_options(
        zerotts
        PRIVATE "/FI${CMAKE_CURRENT_SOURCE_DIR}/windows_fmemopen.h"
    )
endif()
add_executable(omni-zerotts-gguf-server server.cpp)
target_link_libraries(omni-zerotts-gguf-server PRIVATE zerotts)
