import os

def inspect():
    root = "/home/pi/ranbell_image"
    print("Files in root:")
    for item in sorted(os.listdir(root)):
        p = os.path.join(root, item)
        t = "DIR " if os.path.isdir(p) else "FILE"
        print(f"  [{t}] {item}")

if __name__ == "__main__":
    inspect()
