#pragma once

#ifdef _WIN32
#include <cstdio>

static inline FILE *omni_zerotts_fmemopen(void *data, size_t size, const char *) {
    FILE *file = nullptr;
    if (tmpfile_s(&file) != 0 || file == nullptr) {
        return nullptr;
    }
    if (size > 0 && std::fwrite(data, 1, size, file) != size) {
        std::fclose(file);
        return nullptr;
    }
    std::rewind(file);
    return file;
}

#define fmemopen omni_zerotts_fmemopen
#endif
