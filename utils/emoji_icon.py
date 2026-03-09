from PIL import Image, ImageDraw, ImageFont

emoji = "🦞"

size = 512
target = size / 1   # 目标emoji尺寸

img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
draw = ImageDraw.Draw(img)

font_path = "seguiemj.ttf"

# 初始字体大小
font_size = int(target)

font = ImageFont.truetype(font_path, font_size)

# 根据真实bbox微调字体大小
bbox = draw.textbbox((0, 0), emoji, font=font, embedded_color=True)
w = bbox[2] - bbox[0]
h = bbox[3] - bbox[1]

scale = target / max(w, h)
font_size = int(font_size * scale)

font = ImageFont.truetype(font_path, font_size)

bbox = draw.textbbox((0, 0), emoji, font=font, embedded_color=True)
w = bbox[2] - bbox[0]
h = bbox[3] - bbox[1]

# 居中位置
x = (size - w) / 2 - bbox[0]
y = (size - h) / 2 - bbox[1]

draw.text((x, y), emoji, font=font, embedded_color=True)

img.save("assets/emoji.png")