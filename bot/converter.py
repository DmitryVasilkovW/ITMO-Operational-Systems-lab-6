from PIL import Image
import os

def convert_png_to_jpg(png_path):
    img = Image.open(png_path)
    rgb_im = img.convert('RGB')
    rgb_im.save(png_path[:-3] + 'jpg')
