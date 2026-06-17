import os
import json
import requests
from datetime import datetime

from drive import format_size_bytes, is_video_file, is_image_file


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".wma", ".aac"}
DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"}


def _get_file_type_info(filename):
    ext = os.path.splitext(filename or "")[1].lower()
    if is_video_file(filename):
        return "\U0001F3AC", "Grabaci\u00f3n"
    if is_image_file(filename):
        return "\U0001F5BC", "Imagen"
    if ext in AUDIO_EXTENSIONS:
        return "\U0001F3B5", "Audio"
    if ext in DOC_EXTENSIONS:
        return "\U0001F4C4", "Documento"
    return "\U0001F4C1", "Archivo"


def send_to_discord(link, webhook_url, *, thumb_path=None, filename=None, duration=None,
                    folder_name=None, total_files=None, total_size_bytes=None,
                    file_names=None):
    now = datetime.now()
    is_folder = folder_name is not None

    embed = {
        "color": 0x7C3AED,
        "footer": {"text": "Los archivos pueden tardar en procesarse en Google Drive.\n\nViolet Uploader v2"},
    }

    if is_folder:
        embed["title"] = "\U0001F4C1 Contenido Disponible"
        embed["description"] = f"**[Abrir carpeta en Google Drive]({link})**"
        fields = [
            {"name": "Carpeta",  "value": f"`{folder_name}`",            "inline": True},
            {"name": "Archivos", "value": f"`{total_files}`",            "inline": True},
            {"name": "Tama\u00f1o total", "value": f"`{format_size_bytes(total_size_bytes or 0)}`", "inline": True},
            {"name": "Fecha",    "value": now.strftime("%d/%m/%Y"),      "inline": True},
            {"name": "Hora",     "value": now.strftime("%I:%M %p")
                                   .replace("AM","a.m.").replace("PM","p.m."), "inline": True},
        ]
        if file_names:
            max_show = 5
            shown = [f"`{n}`" for n in file_names[:max_show]]
            rest = len(file_names) - max_show
            if rest > 0:
                shown.append(f"y {rest} m\u00e1s")
            fields.append({"name": "Contenido", "value": "\n".join(shown), "inline": False})
        embed["fields"] = fields
    else:
        emoji, label = _get_file_type_info(filename)
        ext = os.path.splitext(filename or "")[1].lstrip(".").upper() or "DESCONOCIDO"
        embed["title"] = f"{emoji} {label} Disponible"
        embed["description"] = f"**[Abrir en Google Drive]({link})**"
        fields = [
            {"name": "Archivo",  "value": f"`{filename or ''}`",          "inline": True},
            {"name": "Formato",  "value": f"`{ext}`",                     "inline": True},
            {"name": "Tama\u00f1o", "value": f"`{format_size_bytes(total_size_bytes or 0)}`", "inline": True},
            {"name": "Fecha",    "value": now.strftime("%d/%m/%Y"),       "inline": True},
            {"name": "Hora",     "value": now.strftime("%I:%M %p")
                                   .replace("AM","a.m.").replace("PM","p.m."), "inline": True},
        ]
        if duration:
            fields.insert(1, {"name": "Duraci\u00f3n", "value": f"`{duration}`", "inline": True})
        embed["fields"] = fields

    files = {}
    if thumb_path and os.path.exists(thumb_path):
        embed["thumbnail"] = {"url": "attachment://thumbnail.jpg"}
        files["file"] = ("thumbnail.jpg", open(thumb_path, "rb"), "image/jpeg")

    payload = {
        "username":   "Violet Uploader",
        "avatar_url": "https://i.imgur.com/QTWoeUF.png",
        "embeds":     [embed],
    }

    data = {"payload_json": json.dumps(payload)}
    r = requests.post(webhook_url, data=data, files=files, timeout=10)

    for f in files.values():
        try:
            f[1].close()
        except Exception:
            pass

    if r.status_code not in (200, 204):
        raise ConnectionError(f"Discord respondi\u00f3 con c\u00f3digo {r.status_code}.")
    return True
