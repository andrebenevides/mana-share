#ifndef MANA_BUILD_ID_DEBUG_H
#define MANA_BUILD_ID_DEBUG_H

#include <string>
#include <sys/types.h>

std::string get_build_id_debug_path(const char *elf_path,
                                    const char *debug_root = nullptr);

off_t get_symbol_offset_with_debug(const char *elf_interpreter,
                                   const char *symbol);

#endif
