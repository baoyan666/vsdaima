from PIL import Image

try:
    png_path = r"C:\Users\86137\Desktop\豆包.png"
    ico_path = r"C:\Users\86137\Desktop\豆包.ico"
    img = Image.open(png_path).convert("RGBA")
    icon_sizes = [(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    print("✅ico生成完成，保存在桌面")
except Exception as e:
    print(f"❌出错：{e}")
