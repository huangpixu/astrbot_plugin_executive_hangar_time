from text_to_img import text_to_image
from pathlib import Path
import os

# 模拟生成的文本内容
text = """🟢【开启时间】>>>>>>🔴【关闭时间】

🟢2026/01/04 17:35:08 🔴2026/01/04 18:40:08

🟢2026/01/04 20:40:09 🔴2026/01/04 21:45:09"""

try:
    # 设置保存目录为当前目录，方便查看
    save_dir = Path("./")
    print(f"Generating image with text:\n{text}\n")
    
    path = text_to_image(text, save_dir)
    
    print(f"Success! Image created at: {path}")
    if os.path.exists(path):
        print(f"File verification: Exists (Size: {os.path.getsize(path)} bytes)")
    else:
        print("File verification: Failed (File not found)")
        
except Exception as e:
    print(f"Error during image generation: {e}")
