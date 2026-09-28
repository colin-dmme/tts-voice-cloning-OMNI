#include "zerotts.h"

#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Rng {
    uint32_t state;
    explicit Rng(uint32_t seed) : state(seed) {}

    float next() {
        state += 0x6d2b79f5u;
        uint32_t value = state;
        value = (value ^ (value >> 15)) * (value | 1u);
        value ^= value + (value ^ (value >> 7)) * (value | 61u);
        return static_cast<float>(
            static_cast<double>(value ^ (value >> 14)) / 4294967296.0
        );
    }
};

std::vector<std::string> split_tabs(const std::string &line) {
    std::vector<std::string> fields;
    std::string field;
    std::istringstream stream(line);
    while (std::getline(stream, field, '\t')) {
        fields.push_back(field);
    }
    return fields;
}

std::vector<int32_t> parse_ids(const std::string &text) {
    std::vector<int32_t> ids;
    std::istringstream stream(text);
    std::string item;
    while (std::getline(stream, item, ',')) {
        if (!item.empty()) {
            ids.push_back(static_cast<int32_t>(std::stoi(item)));
        }
    }
    return ids;
}

std::vector<float> load_voice(const std::string &path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        throw std::runtime_error("cannot read voice latent: " + path);
    }
    file.seekg(0, std::ios::end);
    const std::streamsize bytes = file.tellg();
    file.seekg(0);
    if (bytes <= 0 || bytes % static_cast<std::streamsize>(sizeof(float)) != 0) {
        throw std::runtime_error("voice latent has an invalid byte size");
    }
    std::vector<float> voice(static_cast<size_t>(bytes) / sizeof(float));
    file.read(reinterpret_cast<char *>(voice.data()), bytes);
    return voice;
}

void print_error(const std::string &message) {
    std::cout << "ERR\t" << message << '\n' << std::flush;
}

void generate(zerotts_context *ctx, const std::vector<std::string> &fields) {
    if (fields.size() != 13 || fields[0] != "GENERATE") {
        throw std::runtime_error("invalid request field count");
    }

    const auto ids = parse_ids(fields[12]);
    const auto voice = load_voice(fields[1]);
    if (ids.empty()) {
        throw std::runtime_error("text tokenizer returned no ids");
    }

    const zerotts_hparams *hp = zerotts_hparams_of(ctx);
    const int expected_voice = hp->n_voice_queries * hp->d_model;
    if (static_cast<int>(voice.size()) != expected_voice) {
        throw std::runtime_error("voice latent shape does not match the GGUF model");
    }

    const uint32_t seed = static_cast<uint32_t>(std::stoull(fields[2]));
    const int min_frames = std::stoi(fields[3]);
    const int max_frames = std::stoi(fields[4]);
    const int eoa_extra = std::stoi(fields[5]);

    zerotts_sampling sampling;
    zerotts_sampling_defaults(&sampling);
    sampling.text_temperature = std::stof(fields[6]);
    sampling.text_topk = std::stoi(fields[7]);
    sampling.audio_temperature = std::stof(fields[8]);
    sampling.audio_topk = std::stoi(fields[9]);
    sampling.audio_topp = std::stof(fields[10]);
    sampling.audio_repetition_penalty = std::stof(fields[11]);

    if (zerotts_begin(ctx, ids.data(), static_cast<int>(ids.size()), voice.data()) != 0) {
        throw std::runtime_error("zerotts_begin failed");
    }

    Rng rng(seed);
    const int codebooks = hp->num_codebooks;
    std::vector<int32_t> codes(codebooks);
    std::vector<float> audio_uniforms(codebooks);
    std::vector<std::vector<int32_t>> frames;
    int tail_left = -1;

    for (int frame_index = 0;; ++frame_index) {
        const bool forbid_eoa = frame_index < min_frames || tail_left >= 0;
        const float control_uniform = rng.next();
        for (float &value : audio_uniforms) {
            value = rng.next();
        }

        int is_eoa = 0;
        if (zerotts_frame(
                ctx,
                forbid_eoa,
                &sampling,
                control_uniform,
                audio_uniforms.data(),
                codes.data(),
                &is_eoa
            ) != 0) {
            throw std::runtime_error("zerotts_frame failed");
        }
        if (tail_left < 0 && is_eoa) {
            tail_left = eoa_extra;
        }
        if ((tail_left >= 0 && tail_left <= 0) || frame_index >= max_frames) {
            break;
        }

        frames.push_back(codes);
        if (tail_left >= 0 && --tail_left <= 0) {
            break;
        }
        if (zerotts_advance(ctx, codes.data(), frame_index) != 0) {
            throw std::runtime_error("zerotts_advance failed");
        }
    }

    std::cout << "OK\t[";
    for (size_t frame = 0; frame < frames.size(); ++frame) {
        std::cout << (frame ? ",[" : "[");
        for (int codebook = 0; codebook < codebooks; ++codebook) {
            std::cout << (codebook ? "," : "") << frames[frame][codebook];
        }
        std::cout << "]";
    }
    std::cout << "]\n" << std::flush;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc != 3) {
        std::cerr << "usage: omni-zerotts-gguf-server model.gguf threads\n";
        return 1;
    }

    const int threads = std::atoi(argv[2]);
    zerotts_context *ctx = zerotts_init_from_file(argv[1], threads);
    if (!ctx) {
        std::cerr << "failed to load GGUF model: " << argv[1] << '\n';
        return 1;
    }

    const zerotts_hparams *hp = zerotts_hparams_of(ctx);
    std::cout << "READY\t" << hp->num_codebooks << '\n' << std::flush;

    std::string line;
    while (std::getline(std::cin, line)) {
        try {
            generate(ctx, split_tabs(line));
        } catch (const std::exception &error) {
            print_error(error.what());
        }
    }

    zerotts_free(ctx);
    return 0;
}
