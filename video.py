import os
import cv2


def get_video_duration(filepath):
    cap = cv2.VideoCapture(filepath)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    secs = int(frames / fps) if fps > 0 else 0
    return f"{secs // 60}:{secs % 60:02d}"


def extract_thumbnail(filepath):
    cap = cv2.VideoCapture(filepath)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    target = int(total * 0.10)
    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    thumb_path = filepath.rsplit(".", 1)[0] + "_thumb.jpg"
    cv2.imwrite(thumb_path, frame)
    return thumb_path


def extract_image_thumbnail(filepath):
    img = cv2.imread(filepath)
    if img is None:
        return None
    thumb_path = filepath.rsplit(".", 1)[0] + "_thumb.jpg"
    cv2.imwrite(thumb_path, img)
    return thumb_path
