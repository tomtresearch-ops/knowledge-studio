#!/usr/bin/env python3
"""
Create custom icons for YouTube Intelligence Server apps
"""

from PIL import Image, ImageDraw, ImageFont
import os
import math

def create_start_icon():
    """Create a green play button icon for start server"""
    # Create a 512x512 image with transparent background
    img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw outer circle (green)
    draw.ellipse([50, 50, 462, 462], fill=(34, 197, 94, 255), outline=(22, 163, 74, 255), width=8)
    
    # Draw inner circle (darker green)
    draw.ellipse([100, 100, 412, 412], fill=(22, 163, 74, 255))
    
    # Draw play triangle
    triangle_points = [
        (180, 150),  # Left point
        (180, 362),  # Bottom left
        (332, 256)   # Right point
    ]
    draw.polygon(triangle_points, fill=(255, 255, 255, 255))
    
    # Add "YT" text
    try:
        # Try to use a system font
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    # Draw "YT" text
    draw.text((256, 400), "YT", fill=(255, 255, 255, 255), font=font, anchor="mm")
    
    return img

def create_stop_icon():
    """Create a red stop button icon for stop server"""
    # Create a 512x512 image with transparent background
    img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw outer circle (red)
    draw.ellipse([50, 50, 462, 462], fill=(239, 68, 68, 255), outline=(220, 38, 38, 255), width=8)
    
    # Draw inner circle (darker red)
    draw.ellipse([100, 100, 412, 412], fill=(220, 38, 38, 255))
    
    # Draw stop square
    draw.rectangle([180, 180, 332, 332], fill=(255, 255, 255, 255))
    
    # Add "YT" text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    # Draw "YT" text
    draw.text((256, 400), "YT", fill=(255, 255, 255, 255), font=font, anchor="mm")
    
    return img

def create_restart_icon():
    """Create an orange/amber refresh/reload icon for restart server"""
    # Create a 512x512 image with transparent background
    img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw outer circle (orange/amber - matches "Restarting..." UI color)
    draw.ellipse([50, 50, 462, 462], fill=(245, 158, 11, 255), outline=(217, 119, 6, 255), width=8)
    
    # Draw inner circle (darker amber)
    draw.ellipse([100, 100, 412, 412], fill=(217, 119, 6, 255))
    
    # Draw circular refresh/reload symbol (two curved arrows)
    # Center point
    center_x, center_y = 256, 256
    radius = 80
    
    # Draw the circular refresh symbol
    # Draw curved arrow 1 (top-right to bottom-left)
    # Arc from ~45 degrees to ~225 degrees
    bbox1 = [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
    draw.arc(bbox1, start=45, end=225, fill=(255, 255, 255, 255), width=12)
    
    # Arrowhead 1 (at end of first arc - bottom-left)
    arrow1_x = center_x + radius * math.cos(math.radians(225))
    arrow1_y = center_y + radius * math.sin(math.radians(225))
    arrow1_points = [
        (arrow1_x, arrow1_y),
        (arrow1_x - 15, arrow1_y - 8),
        (arrow1_x - 8, arrow1_y - 15)
    ]
    draw.polygon(arrow1_points, fill=(255, 255, 255, 255))
    
    # Draw curved arrow 2 (bottom-left to top-right, overlapping)
    # Arc from ~225 degrees to ~405 (45) degrees
    bbox2 = [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
    draw.arc(bbox2, start=225, end=405, fill=(255, 255, 255, 255), width=12)
    
    # Arrowhead 2 (at end of second arc - top-right)
    arrow2_x = center_x + radius * math.cos(math.radians(45))
    arrow2_y = center_y + radius * math.sin(math.radians(45))
    arrow2_points = [
        (arrow2_x, arrow2_y),
        (arrow2_x - 15, arrow2_y + 8),
        (arrow2_x - 8, arrow2_y + 15)
    ]
    draw.polygon(arrow2_points, fill=(255, 255, 255, 255))
    
    # Add "YT" text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    # Draw "YT" text
    draw.text((256, 400), "YT", fill=(255, 255, 255, 255), font=font, anchor="mm")
    
    return img

def create_server_icon():
    """Create a server/network icon for general server apps"""
    # Create a 512x512 image with transparent background
    img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw outer circle (blue)
    draw.ellipse([50, 50, 462, 462], fill=(59, 130, 246, 255), outline=(37, 99, 235, 255), width=8)
    
    # Draw inner circle (darker blue)
    draw.ellipse([100, 100, 412, 412], fill=(37, 99, 235, 255))
    
    # Draw server rack
    # Main rectangle
    draw.rectangle([150, 180, 362, 340], fill=(255, 255, 255, 255))
    
    # Server slots
    for i in range(4):
        y = 200 + i * 30
        draw.rectangle([170, y, 342, y + 20], fill=(59, 130, 246, 255))
    
    # Add "YT" text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    # Draw "YT" text
    draw.text((256, 400), "YT", fill=(255, 255, 255, 255), font=font, anchor="mm")
    
    return img

def main():
    print("🎨 Creating custom icons for YouTube Intelligence Server...")
    
    # Create icons directory
    os.makedirs("icons", exist_ok=True)
    
    # Create start icon
    start_icon = create_start_icon()
    start_icon.save("icons/start_server_icon.png")
    print("✅ Created start icon: icons/start_server_icon.png")
    
    # Create stop icon
    stop_icon = create_stop_icon()
    stop_icon.save("icons/stop_server_icon.png")
    print("✅ Created stop icon: icons/stop_server_icon.png")
    
    # Create restart icon
    restart_icon = create_restart_icon()
    restart_icon.save("icons/restart_server_icon.png")
    print("✅ Created restart icon: icons/restart_server_icon.png")
    
    # Create server icon
    server_icon = create_server_icon()
    server_icon.save("icons/server_icon.png")
    print("✅ Created server icon: icons/server_icon.png")
    
    print("\n🎯 Icons created! Now applying them to the apps...")
    
    # Apply icons to the apps
    os.system('sips -s format icns icons/start_server_icon.png --out "Start YouTube Server.app/Contents/Resources/icon.icns"')
    os.system('sips -s format icns icons/stop_server_icon.png --out "Stop YouTube Server.app/Contents/Resources/icon.icns"')
    os.system('sips -s format icns icons/restart_server_icon.png --out "Restart YouTube Server.app/Contents/Resources/icon.icns"')
    
    print("✅ Icons applied to apps!")
    print("\n🚀 Your apps now have custom icons:")
    print("   - Start YouTube Server.app (Green play button)")
    print("   - Stop YouTube Server.app (Red stop button)")
    print("   - Restart YouTube Server.app (Orange refresh/reload symbol)")
    print("\n📱 Drag them to your Dock - they'll look professional and distinctive!")

if __name__ == "__main__":
    main()


