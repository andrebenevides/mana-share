#include "build-id-debug.h"

#include <stdio.h>
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>

#include <string>
#include <vector>

namespace {

size_t align_note_value(size_t value)
{
    return (value + 3U) & ~static_cast<size_t>(3U);
}

bool read_exact_at(int fd, void *buffer, size_t size, off_t offset)
{
    unsigned char *cursor = static_cast<unsigned char *>(buffer);
    size_t remaining = size;

    while (remaining > 0) {
        ssize_t result = pread(fd, cursor, remaining, offset);
        if (result < 0 && errno == EINTR) {
            continue;
        }
        if (result <= 0) {
            return false;
        }
        cursor += result;
        remaining -= static_cast<size_t>(result);
        offset += result;
    }
    return true;
}

std::string build_id_from_elf(const char *path)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        return "";
    }

    struct stat info;
    const unsigned short endian_probe = 1;
    const int native_encoding =
        *reinterpret_cast<const unsigned char *>(&endian_probe)
        ? ELFDATA2LSB : ELFDATA2MSB;
    Elf64_Ehdr header;
    if (fstat(fd, &info) != 0 || info.st_size < 0 ||
        !read_exact_at(fd, &header, sizeof(header), 0) ||
        memcmp(header.e_ident, ELFMAG, SELFMAG) != 0 ||
        header.e_ident[EI_CLASS] != ELFCLASS64 ||
        header.e_ident[EI_DATA] != native_encoding ||
        header.e_ident[EI_VERSION] != EV_CURRENT ||
        header.e_version != EV_CURRENT ||
        header.e_phentsize != sizeof(Elf64_Phdr)) {
        close(fd);
        return "";
    }

    const auto file_size = static_cast<Elf64_Xword>(info.st_size);
    if (header.e_phoff > file_size ||
        header.e_phnum > (file_size - header.e_phoff) / sizeof(Elf64_Phdr)) {
        close(fd);
        return "";
    }
    std::vector<Elf64_Phdr> program_headers(header.e_phnum);
    if (!read_exact_at(fd,
                       program_headers.data(),
                       program_headers.size() * sizeof(Elf64_Phdr),
                       header.e_phoff)) {
        close(fd);
        return "";
    }

    std::string build_id;
    for (const Elf64_Phdr &program_header : program_headers) {
        if (program_header.p_type != PT_NOTE ||
            program_header.p_filesz < sizeof(Elf64_Nhdr) ||
            program_header.p_offset > file_size ||
            program_header.p_filesz > file_size - program_header.p_offset) {
            continue;
        }

        std::vector<unsigned char> notes(program_header.p_filesz);
        if (!read_exact_at(fd,
                           notes.data(),
                           notes.size(),
                           program_header.p_offset)) {
            continue;
        }

        size_t cursor = 0;
        while (cursor + sizeof(Elf64_Nhdr) <= notes.size()) {
            Elf64_Nhdr note_header;
            memcpy(&note_header, notes.data() + cursor, sizeof(note_header));
            cursor += sizeof(note_header);

            const size_t name_offset = cursor;
            const size_t aligned_name = align_note_value(note_header.n_namesz);
            if (aligned_name > notes.size() - cursor) {
                break;
            }
            cursor += aligned_name;

            const size_t description_offset = cursor;
            const size_t aligned_description =
                align_note_value(note_header.n_descsz);
            if (aligned_description > notes.size() - cursor) {
                break;
            }
            cursor += aligned_description;

            const bool gnu_note =
                note_header.n_namesz == 4 &&
                name_offset + note_header.n_namesz <= notes.size() &&
                memcmp(notes.data() + name_offset, "GNU", 4) == 0;

            if (!gnu_note || note_header.n_type != NT_GNU_BUILD_ID ||
                description_offset + note_header.n_descsz > notes.size()) {
                continue;
            }

            static const char hexadecimal[] = "0123456789abcdef";
            build_id.reserve(note_header.n_descsz * 2U);
            for (size_t index = 0; index < note_header.n_descsz; ++index) {
                const unsigned char value =
                    notes[description_offset + index];
                build_id.push_back(hexadecimal[value >> 4]);
                build_id.push_back(hexadecimal[value & 0x0f]);
            }
            break;
        }

        if (!build_id.empty()) {
            break;
        }
    }

    close(fd);
    return build_id;
}

}  // namespace

std::string get_build_id_debug_path(const char *elf_path,
                                    const char *debug_root)
{
    if (elf_path == nullptr || *elf_path == '\0') {
        return "";
    }

    char resolved_path[PATH_MAX];
    if (realpath(elf_path, resolved_path) == nullptr) {
        return "";
    }

    const std::string build_id = build_id_from_elf(resolved_path);
    if (build_id.size() < 3) {
        return "";
    }

    if (debug_root == nullptr || *debug_root == '\0') {
        debug_root = getenv("MANA_DEBUG_ROOT");
    }
    if (debug_root == nullptr || *debug_root == '\0') {
        debug_root = "/usr/lib/debug";
    }

    std::string result(debug_root);
    while (result.size() > 1 && result.back() == '/') {
        result.pop_back();
    }
    result += "/.build-id/";
    result += build_id.substr(0, 2);
    result += "/";
    result += build_id.substr(2);
    result += ".debug";
    return result;
}

// Compiled as C++ by the lower-half Makefile.
off_t get_symbol_offset(const char *pathname, const char *symbol);

// Try embedded/legacy symbols, then conventional and GNU build-ID debug files.
off_t
get_symbol_offset_with_debug(const char *elf_interpreter, const char *symbol)
{
  off_t offset = get_symbol_offset(elf_interpreter, symbol);
  if (offset) {
    return offset;
  }

  char resolved_path[PATH_MAX];
  const bool resolved = realpath(elf_interpreter, resolved_path) != nullptr;
  const std::string conventional_path = resolved
    ? std::string("/usr/lib/debug") + resolved_path : "";
  if (!conventional_path.empty() && access(conventional_path.c_str(), R_OK) == 0) {
    fprintf(stderr, "Debug symbols for interpreter in: %s\n",
            conventional_path.c_str());
    offset = get_symbol_offset(conventional_path.c_str(), symbol);
    if (offset) {
      return offset;
    }
  }

  const std::string build_id_path = get_build_id_debug_path(
    elf_interpreter,
    getenv("MANA_DEBUG_ROOT")
  );
  if (!build_id_path.empty() && access(build_id_path.c_str(), R_OK) == 0) {
    fprintf(stderr,
            "Debug symbols for interpreter in: %s\n",
            build_id_path.c_str());
    offset = get_symbol_offset(build_id_path.c_str(), symbol);
    if (offset) {
      return offset;
    }
  }

  fprintf(stderr,
          "Unable to find symbol %s in %s or its detached debug files.\n",
          symbol,
          elf_interpreter);
  if (!conventional_path.empty()) {
    fprintf(stderr, "Tried: %s\n", conventional_path.c_str());
  }
  if (!build_id_path.empty()) {
    fprintf(stderr, "Tried: %s\n", build_id_path.c_str());
  }
  fprintf(stderr, "Install matching loader debug symbols (libc6-dbg on Ubuntu),\n"
                  "or set MANA_DEBUG_ROOT to their debug root.\n");
  abort();
}
