from pathlib import Path


def main():
    import os

    from text_to_img import text_to_image

    text = """🟢【开启时间】>>>>>>🔴【关闭时间】

🟢2026/01/04 17:35:08 🔴2026/01/04 18:40:08

🟢2026/01/04 20:40:09 🔴2026/01/04 21:45:09"""

    save_dir = Path("./")
    print(f"Generating image with text:\n{text}\n")

    path = text_to_image(text, save_dir)
    print(f"Success! Image created at: {path}")

    if os.path.exists(path):
        print(f"File verification: Exists (Size: {os.path.getsize(path)} bytes)")
    else:
        print("File verification: Failed (File not found)")


if __name__ == "__main__":
    main()
