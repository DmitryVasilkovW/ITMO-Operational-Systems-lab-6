from PIL import Image

def convert_png_to_jpg(png_path):
    img = Image.open(png_path)
    rgb_im = img.convert('RGB')
    rgb_im.save(png_path[:-3] + 'jpg')

def create_empty_jpg(png_path):
    jpg_path = png_path[:-3] + 'jpg'
    open(jpg_path, 'a').close()