import os
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

from config_module import TOKEN_PICKLE

VIOLET_FOLDER_NAME = "Violet Uploads"


def format_size_bytes(b):
    if b >= 1_073_741_824:
        return f"{b/1_073_741_824:.2f} GB"
    if b >= 1_048_576:
        return f"{b/1_048_576:.2f} MB"
    if b > 0:
        return f"{b/1024:.1f} KB"
    return "N/A"


def is_logged_in():
    if not os.path.exists(TOKEN_PICKLE):
        return False
    try:
        with open(TOKEN_PICKLE, "rb") as f:
            creds = pickle.load(f)
        return bool(creds and (creds.valid or (creds.expired and creds.refresh_token)))
    except Exception:
        return False


def get_google_account_email():
    if not is_logged_in():
        return None
    try:
        with open(TOKEN_PICKLE, "rb") as f:
            creds = pickle.load(f)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        service = build("oauth2", "v2", credentials=creds)
        info = service.userinfo().get().execute()
        return info.get("email")
    except Exception:
        return None


def get_drive_service():
    with open(TOKEN_PICKLE, "rb") as f:
        creds = pickle.load(f)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PICKLE, "wb") as f:
            pickle.dump(creds, f)
    return build("drive", "v3", credentials=creds)


def get_or_create_violet_folder(service):
    """Busca la carpeta 'Violet Uploads' en Drive, o la crea si no existe."""
    response = service.files().list(
        q=f"name='{VIOLET_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    files = response.get('files', [])
    if files:
        return files[0]['id']
    folder = service.files().create(
        body={'name': VIOLET_FOLDER_NAME, 'mimeType': 'application/vnd.google-apps.folder'},
        fields='id'
    ).execute()
    return folder.get('id')


def upload_to_drive(filepath, cancel_event, display_name=None, folder_id=None, service=None):
    if service is None:
        service = get_drive_service()
    body = {"name": display_name or os.path.basename(filepath)}
    if folder_id:
        body["parents"] = [folder_id]
    media = MediaFileUpload(filepath, resumable=True)
    request = service.files().create(body=body, media_body=media, fields="id")
    response = None
    while response is None:
        if cancel_event.is_set():
            raise InterruptedError("Subida cancelada por el usuario.")
        _, response = request.next_chunk()
    file_id = response.get("id")
    service.permissions().create(
        fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
    return file_id


def create_drive_folder(name, parent_id=None, service=None):
    if service is None:
        service = get_drive_service()
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    result = service.files().create(body=body, fields="id").execute()
    return result.get("id")


def ensure_drive_path(relative_path, root_folder_id, service=None, cache=None, track_ids=None):
    if service is None:
        service = get_drive_service()
    if cache is None:
        cache = {}
    parts = os.path.normpath(relative_path).replace("\\", "/").split("/")
    parts = [p for p in parts if p and p != "."]
    if not parts:
        return root_folder_id
    parent_id = root_folder_id
    for i, part in enumerate(parts):
        path_sofar = "/".join(parts[:i + 1])
        if path_sofar in cache:
            parent_id = cache[path_sofar]
            continue
        q = (f"name='{part}' and mimeType='application/vnd.google-apps.folder' "
             f"and '{parent_id}' in parents and trashed=false")
        res = service.files().list(q=q, spaces="drive", fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            parent_id = files[0]["id"]
        else:
            parent_id = create_drive_folder(part, parent_id=parent_id, service=service)
            if track_ids is not None:
                track_ids.append(parent_id)
        cache[path_sofar] = parent_id
    return parent_id


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".m4v"}


def is_video_file(filename):
    _, ext = os.path.splitext(filename)
    return ext.lower() in VIDEO_EXTENSIONS


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def is_image_file(filename):
    _, ext = os.path.splitext(filename)
    return ext.lower() in IMAGE_EXTENSIONS
