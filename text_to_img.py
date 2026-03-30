from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import re
import requests
import os

def download_font(font_path: Path):
    """Download Noto Sans SC font if not exists."""
    url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
    # Alternative URL if the above fails or is slow?
    # For now, we stick to the official repo. 
    
    print(f"Downloading font from {url}...")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        font_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(font_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Font downloaded successfully.")
        return True
    except Exception as e:
        print(f"Failed to download font: {e}")
        return False

def get_font(size: int, data_dir: Path):
    """Load font, downloading it if necessary."""
    # Try system font first (for local testing speed)
    system_fonts = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc" # macOS
    ]
    
    for sf in system_fonts:
        if os.path.exists(sf):
            try:
                return ImageFont.truetype(sf, size)
            except:
                pass

    # If system font not found, look for local font in data_dir
    font_filename = "NotoSansCJKsc-Regular.otf"
    font_path = data_dir / "fonts" / font_filename
    
    if not font_path.exists():
        # Try to download
        if not download_font(font_path):
            # If download fails, return default (will look ugly/narrow but better than crash)
            print("Using default font as fallback.")
            return ImageFont.load_default()
            
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception as e:
        print(f"Error loading downloaded font: {e}")
        return ImageFont.load_default()

def text_to_image(text: str, save_dir: Path) -> str:
    """
    Convert text to an image and return the file path.
    Replaces 🟢 and 🔴 with drawn circles to avoid font issues.
    Downloads font if missing to ensure correct width calculation and rendering.
    """
    font_size = 20
    line_spacing = 6 # Increased spacing
    
    # Load font
    font = get_font(font_size, save_dir)
    
    # Define emoji markers
    GREEN_MARKER = "🟢"
    RED_MARKER = "🔴"
    
    lines = text.split('\n')
    
    # Calculate image size
    max_width = 0
    total_height = 0
    
    # Use a dummy draw to measure text
    dummy_img = Image.new('RGB', (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    
    # Height of a single line
    # Measure a standard character
    bbox = dummy_draw.textbbox((0, 0), "Hg", font=font)
    line_height = bbox[3] - bbox[1]
    line_height = max(line_height, font_size)
    
    parsed_lines = []
    
    for line in lines:
        parts = re.split(f'({GREEN_MARKER}|{RED_MARKER})', line)
        parts = [p for p in parts if p] 
        
        line_width = 0
        line_parts_data = []
        
        for part in parts:
            if part in [GREEN_MARKER, RED_MARKER]:
                w = font_size + 4 # Add a little space around emoji
                line_parts_data.append({'type': 'emoji', 'content': part, 'width': w})
                line_width += w
            else:
                w = dummy_draw.textlength(part, font=font)
                line_parts_data.append({'type': 'text', 'content': part, 'width': w})
                line_width += w
                
        parsed_lines.append(line_parts_data)
        max_width = max(max_width, line_width)
        total_height += line_height + line_spacing

    if total_height > 0:
        total_height -= line_spacing

    # Add padding
    padding_x = 30 # Increased horizontal padding
    padding_y = 20
    img_width = int(max_width + 2 * padding_x)
    img_height = int(total_height + 2 * padding_y)
    
    # Create image
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    current_y = padding_y
    
    for line_parts in parsed_lines:
        current_x = padding_x
        
        for part in line_parts:
            if part['type'] == 'emoji':
                # Draw circle
                circle_size = font_size * 0.8
                
                # Center horizontally in the allocated slot
                # part['width'] is the slot width
                x_offset = (part['width'] - circle_size) / 2
                draw_x = current_x + x_offset
                
                # Center vertically with offset
                vertical_adjustment = 4
                y_offset = (line_height - circle_size) / 2 + vertical_adjustment
                draw_y = current_y + y_offset
                
                color = "#2ecc71" if part['content'] == GREEN_MARKER else "red"
                draw.ellipse(
                    [draw_x, draw_y, draw_x + circle_size, draw_y + circle_size],
                    fill=color,
                    outline=None
                )
                
                current_x += part['width']
            else:
                draw.text((current_x, current_y), part['content'], font=font, fill='black')
                current_x += part['width']
        
        current_y += line_height + line_spacing
    
    if not save_dir.exists():
        save_dir.mkdir(parents=True, exist_ok=True)
        
    output_path = save_dir / "hangar_time_schedule.png"
    img.save(output_path)
    
    return str(output_path)

def members_to_image(members: list, save_dir: Path) -> str:
    """
    Generate an image for the members list.
    """
    font_size = 20
    line_spacing = 8
    
    font = get_font(font_size, save_dir)
    
    dummy_img = Image.new('RGB', (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    
    bbox = dummy_draw.textbbox((0, 0), "Hg", font=font)
    line_height = bbox[3] - bbox[1]
    line_height = max(line_height, font_size)
    
    lines_data = []
    
    # Title
    title_text = f"【鹿港成员名单】 (共 {len(members)} 人)"
    lines_data.append({"text": title_text, "color": "black", "is_title": True})
    lines_data.append({"text": "-" * 40, "color": "gray", "is_title": False})
    
    for idx, member in enumerate(members, start=1):
        handle = member.get("handle", "")
        moniker = member.get("moniker", "")
        rank = member.get("rank", "")
        stars = member.get("stars", 0)
        color_level = member.get("color_level", "black")
        is_hidden = member.get("is_hidden", False)
        
        # Build stars string (e.g. ★★★★★)
        stars_str = "★" * stars if stars > 0 else ""
        
        if is_hidden:
            line_text = f"{idx}. 隐藏成员"
            color = "gray"
        else:
            rank_display = f"{rank} {stars_str}".strip()
            line_text = f"{idx}. {handle} ({moniker}) - {rank_display}"
            if color_level == "red":
                color = "red"
            elif color_level == "blue":
                color = "#0066cc" # Use a nice readable blue
            else:
                color = "black"
            
        lines_data.append({"text": line_text, "color": color, "is_title": False})
        
    max_width = 0
    for line in lines_data:
        w = dummy_draw.textlength(line["text"], font=font)
        max_width = max(max_width, w)
        
    padding_x = 40
    padding_y = 30
    
    img_width = int(max_width + 2 * padding_x)
    img_height = int(len(lines_data) * (line_height + line_spacing) + 2 * padding_y)
    
    img = Image.new('RGB', (img_width, img_height), color='#f9f9f9')
    draw = ImageDraw.Draw(img)
    
    current_y = padding_y
    for line in lines_data:
        draw.text((padding_x, current_y), line["text"], font=font, fill=line["color"])
        current_y += line_height + line_spacing
        
    if not save_dir.exists():
        save_dir.mkdir(parents=True, exist_ok=True)
        
    output_path = save_dir / "lugang_members.png"
    img.save(output_path)
    
    return str(output_path)
