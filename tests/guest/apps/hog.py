def main() -> bool:
    held = []
    print("hog: started")
    while True:
        held.append(bytearray(65536))
