from PIL import Image, ImageOps
import numpy as np
from PySide6 import QtGui, QtCore

def get_exif_orientation(img_path):
    """Returns the EXIF orientation tag value (1-8) or None."""
    try:
        with Image.open(img_path) as img:
            exif = img.getexif()
            if exif:
                return exif.get(0x0112) # 274 is the Orientation tag
    except:
        pass
    return None

def rotate_cv2_image(img, orientation):
    """Rotates an OpenCV BGR image based on EXIF orientation tag."""
    import cv2
    if orientation == 2:
        return cv2.flip(img, 1)
    elif orientation == 3:
        return cv2.rotate(img, cv2.ROTATE_180)
    elif orientation == 4:
        return cv2.flip(img, 0)
    elif orientation == 5:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        return cv2.flip(img, 1)
    elif orientation == 6:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif orientation == 7:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return cv2.flip(img, 1)
    elif orientation == 8:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img

def rotate_qimage(image, orientation):
    """Rotates a QImage based on EXIF orientation tag."""
    transform = QtGui.QTransform()
    if orientation == 2:
        transform.scale(-1, 1)
    elif orientation == 3:
        transform.rotate(180)
    elif orientation == 4:
        transform.scale(1, -1)
    elif orientation == 5:
        transform.rotate(90)
        transform.scale(-1, 1)
    elif orientation == 6:
        transform.rotate(90)
    elif orientation == 7:
        transform.rotate(-90)
        transform.scale(-1, 1)
    elif orientation == 8:
        transform.rotate(-90)
    
    if not transform.isIdentity():
        return image.transformed(transform, QtCore.Qt.SmoothTransformation)
    return image

def load_image_correct_orientation(img_path):
    """Loads an image using Pillow and corrects orientation. Returns PIL Image."""
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img)
    return img
