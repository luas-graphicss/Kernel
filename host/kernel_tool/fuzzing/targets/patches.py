PATCH_OFFSET_BYTES = 3
PATCH_HEADER_BYTES = PATCH_OFFSET_BYTES + 1
MAX_PATCH_BYTES = 16


def apply_patches(image: bytes, script: bytes) -> bytes:
    if not image:
        return image
    edited = bytearray(image)
    position = 0
    while position + PATCH_HEADER_BYTES <= len(script):
        offset = int.from_bytes(script[position : position + PATCH_OFFSET_BYTES], "little")
        offset %= len(edited)
        length = script[position + PATCH_OFFSET_BYTES] % MAX_PATCH_BYTES + 1
        position += PATCH_HEADER_BYTES
        patch = script[position : position + length][: len(edited) - offset]
        edited[offset : offset + len(patch)] = patch
        position += length
    return bytes(edited)
