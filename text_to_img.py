from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import re

def text_to_image(text: str, save_dir: Path) -> str:
    """
    Convert text to an image and return the file path.
    Replaces 🟢 and 🔴 with drawn circles to avoid font issues.
    """
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    font_size = 20
    line_spacing = 4
    
    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        font = ImageFont.load_default()

    # Define emoji markers
    GREEN_MARKER = "🟢"
    RED_MARKER = "🔴"
    
    lines = text.split('\n')
    
    # Calculate image size
    # We need to simulate drawing to get the width
    max_width = 0
    total_height = 0
    
    # Use a dummy draw to measure text
    dummy_img = Image.new('RGB', (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    
    # Height of a single line (approximation using 'Hg')
    bbox = dummy_draw.textbbox((0, 0), "Hg", font=font)
    line_height = bbox[3] - bbox[1]
    # Ensure line height is at least font_size (for emojis)
    line_height = max(line_height, font_size)
    
    parsed_lines = []
    
    for line in lines:
        # Split line by markers, keeping delimiters
        parts = re.split(f'({GREEN_MARKER}|{RED_MARKER})', line)
        parts = [p for p in parts if p] # Remove empty strings
        
        line_width = 0
        line_parts_data = []
        
        for part in parts:
            if part in [GREEN_MARKER, RED_MARKER]:
                # Emoji width - assume square based on font size
                w = font_size
                line_parts_data.append({'type': 'emoji', 'content': part, 'width': w})
                line_width += w
            else:
                # Text width
                w = dummy_draw.textlength(part, font=font)
                line_parts_data.append({'type': 'text', 'content': part, 'width': w})
                line_width += w
                
        parsed_lines.append(line_parts_data)
        max_width = max(max_width, line_width)
        total_height += line_height + line_spacing

    # Remove last spacing
    if total_height > 0:
        total_height -= line_spacing

    # Add padding
    padding = 20
    img_width = int(max_width + 2 * padding)
    img_height = int(total_height + 2 * padding)
    
    # Create image
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    current_y = padding
    
    for line_parts in parsed_lines:
        current_x = padding
        
        # Center the content vertically within the line
        # line_height is the allocated height for the line
        
        for part in line_parts:
            if part['type'] == 'emoji':
                # Draw circle
                # Center circle in the line height
                circle_size = font_size * 0.8
                
                # Center horizontally in the allocated slot (width=font_size)
                x_offset = (font_size - circle_size) / 2
                draw_x = current_x + x_offset
                
                # Center vertically
                # Add a small offset to push it down slightly to match text baseline better
                vertical_adjustment = 6
                y_offset = (line_height - circle_size) / 2 + vertical_adjustment
                draw_y = current_y + y_offset
                
                # Use a lighter green color, but keep standard red as requested
                color = "#2ecc71" if part['content'] == GREEN_MARKER else "red"
                draw.ellipse(
                    [draw_x, draw_y, draw_x + circle_size, draw_y + circle_size],
                    fill=color,
                    outline=None
                )
                
                current_x += part['width']
            else:
                # Draw text
                # Align text to be roughly vertically centered or baseline aligned
                # Simple approach: Top align with some adjustment or center
                
                # Let's try to center it vertically relative to line_height
                # Get text height
                # bbox = draw.textbbox((0, 0), part['content'], font=font)
                # h = bbox[3] - bbox[1]
                # y_pos = current_y + (line_height - h) / 2
                # But draw.text uses top-left by default.
                
                # A safer bet for alignment with emojis is just using current_y if line_height ~ font_size
                # But let's add a small offset if needed.
                # Usually text draws from top-left of the bounding box roughly.
                
                draw.text((current_x, current_y), part['content'], font=font, fill='black')
                current_x += part['width']
        
        current_y += line_height + line_spacing
    
    if not save_dir.exists():
        save_dir.mkdir(parents=True, exist_ok=True)
        
    output_path = save_dir / "hangar_time_schedule.png"
    img.save(output_path)
    
    return str(output_path)
