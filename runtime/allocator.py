# tpu_memory.py
# ---------------------------------------------
# Memory allocator for TPU On Chip Memory with free() support.
# Addresses are 13 bit word address (0-8191).
# ---------------------------------------------

MEMORY_SIZE = 8192   # 13-bit depth

class MemoryAllocator:
    def __init__(self):
        self.next_free_addr = 0
        self.memory_map = {}    # name -> (addr, size)
        self.free_list = []     # [(addr, size), ...] - freed blocks available for reuse

    def alloc(self, name, words):
        """
        Allocate 'words' contiguous FP32 entries.
        Returns the starting word address (0-8191).

        Uses first-fit strategy: checks free list first, then bump allocates.
        """
        # First, try to reuse a freed block (first-fit)
        for i, (free_addr, free_size) in enumerate(self.free_list):
            if free_size >= words:
                # Use this block
                self.free_list.pop(i)
                self.memory_map[name] = (free_addr, words)
                # If block is larger, return remainder to free list
                if free_size > words:
                    self.free_list.append((free_addr + words, free_size - words))
                return free_addr

        # No suitable free block, bump allocate
        if (self.next_free_addr + words) > MEMORY_SIZE:
            raise MemoryError(
                f"Out of TPU BRAM: cannot allocate {words} words for '{name}'. "
                f"Used: {self.next_free_addr}, Free list: {len(self.free_list)} blocks"
            )

        addr = self.next_free_addr
        self.next_free_addr += words

        self.memory_map[name] = (addr, words)
        return addr

    def free(self, name):
        """
        Free a previously allocated tensor, making its memory available for reuse.

        Args:
            name: Name of the tensor to free

        Returns:
            Tuple of (addr, size) that was freed, or None if not found
        """
        if name not in self.memory_map:
            return None

        addr, size = self.memory_map.pop(name)
        self.free_list.append((addr, size))
        return (addr, size)

    def get(self, name):
        """Get the starting address of a previously allocated tensor."""
        return self.memory_map[name][0]

    def size(self, name):
        """Get size (words) of a previously allocated tensor."""
        return self.memory_map[name][1]

    def used(self):
        """Get total memory currently in use (excludes freed blocks)."""
        return sum(size for _, size in self.memory_map.values())

    def reset(self):
        """Reset allocator to initial state."""
        self.next_free_addr = 0
        self.memory_map.clear()
        self.free_list.clear()

    def dump(self):
        """Print the memory map."""
        print("\n==== TPU MEMORY MAP ====\n")
        for name, (addr, size) in self.memory_map.items():
            print(f"{name:<15} : addr={addr:5d}, size={size} words")
        print(f"\nAllocated: {self.used()} words")
        print(f"High water mark: {self.next_free_addr} words")
        print(f"Free list: {len(self.free_list)} blocks, {sum(s for _, s in self.free_list)} words")
        print(f"Capacity: {MEMORY_SIZE} words\n")

allocator = MemoryAllocator()
