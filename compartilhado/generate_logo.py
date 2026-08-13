# pyrefly: ignore [missing-import]
from PIL import Image, ImageDraw, ImageFont
import base64
import io

def create_logo():
    # Create a 64x64 transparent image
    size = 64
    img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw a circle for the background (using ACCENT_GOLD #C5A059)
    draw.ellipse((2, 2, size-2, size-2), fill="#C5A059", outline="#0B0F17", width=2)
    
    # Draw text "AC" in the middle
    # Try to use a default Windows font
    try:
        font = ImageFont.truetype("georgiab.ttf", 26)
    except:
        try:
            font = ImageFont.truetype("arialbd.ttf", 26)
        except:
            font = ImageFont.load_default()
            
    text = "AC"
    
    # Using textbbox to center the text
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    
    draw.text(((size-w)/2, (size-h)/2 - 2), text, fill="#0B0F17", font=font)
    
    # Save to memory buffer
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    # Write to Python file
    with open("logo_b64.py", "w") as f:
        f.write(f'LOGO_B64 = "{img_str}"\n')
        
create_logo()
