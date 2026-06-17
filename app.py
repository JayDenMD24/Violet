import os
import sys
import time
import uuid
import socket
import mimetypes
import threading
import json
import base64
import pickle
import wsgiref.simple_server
import webbrowser
from dotenv import load_dotenv, set_key
from flask import Flask, render_template, request, jsonify

mimetypes.add_type('text/css', '.css')
mimetypes.add_type('text/javascript', '.js')

from config_module import ENV_PATH, UPLOAD_DIR, CREDS_JSON, TOKEN_PICKLE, EMAIL_FILE
from drive import (
    format_size_bytes, is_logged_in, get_google_account_email,
    get_drive_service, upload_to_drive, create_drive_folder,
    ensure_drive_path, get_or_create_violet_folder, is_video_file,
    is_image_file,
)
from discord import send_to_discord
from video import get_video_duration, extract_thumbnail, extract_image_thumbnail
from google_auth_oauthlib.flow import InstalledAppFlow, _RedirectWSGIApp

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(UPLOAD_DIR, exist_ok=True)
load_dotenv(ENV_PATH)

app = Flask(__name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static'))
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024

upload_tasks_lock = threading.Lock()
upload_tasks = {}

auth_in_progress = False
auth_lock = threading.Lock()
SAVED_EMAIL = None
pending_flow = {}
auth_error = None

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]


def _extract_email_from_id_token(id_token):
    try:
        parts = id_token.split('.')
        if len(parts) != 3:
            return None
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        return decoded.get('email')
    except Exception:
        return None


# ── PAGES ──

@app.route('/')
def index():
    return render_template('index.html')


# ── API: Config ──

@app.route('/api/config')
def api_config():
    hooks = []
    for i in range(5):
        hooks.append({
            "index": i,
            "name": os.getenv(f"DISCORD_WEBHOOK_NAME_{i}", "").strip(),
            "url": os.getenv(f"DISCORD_WEBHOOK_{i}", "").strip(),
        })
    selected = os.getenv("SELECTED_WEBHOOK", "0").strip()
    return jsonify({
        "logged_in": is_logged_in(),
        "webhooks": hooks,
        "selected_webhook": selected,
    })

@app.route('/api/settings/save', methods=['POST'])
def api_settings_save():
    data = request.json
    for i in range(5):
        set_key(ENV_PATH, f"DISCORD_WEBHOOK_NAME_{i}", data.get(f"name_{i}", "").strip())
        set_key(ENV_PATH, f"DISCORD_WEBHOOK_{i}", data.get(f"url_{i}", "").strip())
    sel = data.get("selected_webhook", "0").strip()
    set_key(ENV_PATH, "SELECTED_WEBHOOK", sel)
    load_dotenv(ENV_PATH, override=True)
    return jsonify({"ok": True})


# ── API: Auth ──

@app.route('/api/auth/status')
def api_auth_status():
    global SAVED_EMAIL
    logged = is_logged_in()
    email = None
    if logged:
        email = SAVED_EMAIL
        if not email:
            try:
                with open(EMAIL_FILE) as f:
                    email = f.read().strip()
            except Exception:
                pass
        if not email:
            email = get_google_account_email()
        if email:
            SAVED_EMAIL = email
    with auth_lock:
        in_progress = auth_in_progress
    return jsonify({"logged_in": logged, "email": email, "auth_in_progress": in_progress, "auth_error": auth_error})

@app.route('/api/auth/start', methods=['POST'])
def api_auth_start():
    global auth_in_progress, pending_flow
    with auth_lock:
        if auth_in_progress:
            return jsonify({"ok": False, "error": "Ya hay un inicio de sesi\u00f3n en curso."})
    if not os.path.exists(CREDS_JSON):
        return jsonify({"ok": False, "error": "Falta credentials.json en la carpeta config/"}), 400
    try:
        flow = InstalledAppFlow.from_client_secrets_file(CREDS_JSON, OAUTH_SCOPES)
        wsgi_app = _RedirectWSGIApp(
            "Autenticaci\u00f3n completada. Puedes cerrar esta ventana."
        )
        wsgiref.simple_server.WSGIServer.allow_reuse_address = False
        local_server = wsgiref.simple_server.make_server(
            '127.0.0.1', 0, wsgi_app
        )
        flow.redirect_uri = f'http://127.0.0.1:{local_server.server_port}/'
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        webbrowser.open(auth_url)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    with auth_lock:
        pending_flow['server'] = local_server
        pending_flow['wsgi'] = wsgi_app
        auth_in_progress = True
    threading.Thread(target=_wait_oauth, args=(flow, wsgi_app, local_server), daemon=True).start()
    return jsonify({"ok": True, "auth_url": auth_url})

def _wait_oauth(flow, wsgi_app, local_server):
    global auth_in_progress, SAVED_EMAIL, auth_error
    auth_error = None
    try:
        local_server.timeout = 1
        while True:
            with auth_lock:
                if not auth_in_progress:
                    return
            local_server.handle_request()
            if wsgi_app.last_request_uri:
                break
        authorization_response = wsgi_app.last_request_uri.replace("http", "https")
        flow.fetch_token(authorization_response=authorization_response)
        creds = flow.credentials
        if creds and creds.valid:
            with open(TOKEN_PICKLE, 'wb') as f:
                pickle.dump(creds, f)
            if hasattr(creds, 'id_token') and creds.id_token:
                SAVED_EMAIL = _extract_email_from_id_token(creds.id_token)
            if not SAVED_EMAIL:
                try:
                    from googleapiclient.discovery import build
                    info = build("oauth2", "v2", credentials=creds).userinfo().get().execute()
                    SAVED_EMAIL = info.get("email")
                except Exception as e:
                    auth_error = f"Error al obtener email: {e}"
            if SAVED_EMAIL:
                try:
                    with open(EMAIL_FILE, 'w') as f:
                        f.write(SAVED_EMAIL)
                except Exception as e:
                    auth_error = f"Error al guardar email: {e}"
    except Exception as e:
        auth_error = str(e)
    finally:
        with auth_lock:
            auth_in_progress = False
            try:
                local_server.server_close()
            except Exception:
                pass
            pending_flow.clear()

@app.route('/api/auth/cancel', methods=['POST'])
def api_auth_cancel():
    with auth_lock:
        if 'server' in pending_flow:
            try:
                pending_flow['server'].socket.close()
            except Exception:
                pass
            auth_in_progress = False
            pending_flow.clear()
    return jsonify({"ok": True})

@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    global SAVED_EMAIL
    try:
        if os.path.exists(TOKEN_PICKLE):
            os.remove(TOKEN_PICKLE)
        SAVED_EMAIL = None
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ── API: Upload ──

@app.route('/api/upload', methods=['POST'])
def api_upload():
    if not is_logged_in():
        return jsonify({"ok": False, "error": "No has iniciado sesi\u00f3n con Google Drive."}), 400

    has_any = any(os.getenv(f"DISCORD_WEBHOOK_{i}", "").strip() for i in range(5))
    if not has_any:
        return jsonify({"ok": False, "error": "No hay ning\u00fan webhook de Discord configurado."}), 400

    webhook_index = request.form.get('webhook_index', '').strip()
    if not webhook_index:
        return jsonify({"ok": False, "error": "No has seleccionado un webhook."}), 400

    webhook_url = os.getenv(f"DISCORD_WEBHOOK_{webhook_index}", "").strip()
    if not webhook_url:
        return jsonify({"ok": False, "error": "El webhook seleccionado no tiene URL configurada."}), 400

    uploaded_files = request.files.getlist('files[]')
    uploaded_paths = request.form.getlist('paths[]')

    if not uploaded_files or len(uploaded_files) != len(uploaded_paths):
        return jsonify({"ok": False, "error": "No se enviaron archivos o falta informaci\u00f3n de rutas."}), 400

    folder_name = request.form.get('folder_name', '').strip() or None
    task_id = str(uuid.uuid4())
    task_dir = os.path.join(UPLOAD_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)

    file_list = []
    for f, rp in zip(uploaded_files, uploaded_paths):
        rp = os.path.normpath(rp).lstrip('.\\/')
        if not rp:
            continue
        dest = os.path.join(task_dir, rp)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        file_list.append((dest, rp))

    if not file_list:
        return jsonify({"ok": False, "error": "No se pudo procesar ning\u00fan archivo."}), 400

    cancel_event = threading.Event()
    with upload_tasks_lock:
        upload_tasks[task_id] = {
            "state": "uploading",
            "message": "Preparando archivos...",
            "progress": 0,
            "cancel_event": cancel_event,
            "filename": folder_name or os.path.basename(file_list[0][1]),
            "total_files": len(file_list),
            "log": [],
        }

    threading.Thread(
        target=_process_upload,
        args=(task_id, task_dir, file_list, folder_name, webhook_index, cancel_event),
        daemon=True
    ).start()

    return jsonify({"ok": True, "task_id": task_id})

def _process_upload(task_id, task_dir, file_list, folder_name, webhook_index, cancel_event):

    def update(msg, progress, state="uploading"):
        with upload_tasks_lock:
            if task_id in upload_tasks:
                upload_tasks[task_id]["message"] = msg
                upload_tasks[task_id]["progress"] = progress
                upload_tasks[task_id]["state"] = state

    def log_msg(msg):
        with upload_tasks_lock:
            if task_id in upload_tasks:
                upload_tasks[task_id]["log"].append(msg)

    def check_cancel():
        if cancel_event.is_set():
            raise InterruptedError("Subida cancelada por el usuario.")

    uploaded_ids = []
    path_cache = {}
    service = None
    thumb_path = None
    first_video_duration = None
    drive_root_id = None

    try:
        update("Preparando archivos...", 0)
        total = len(file_list)
        check_cancel()

        service = get_drive_service()
        log_msg("Conexi\u00f3n con Google Drive establecida")
        check_cancel()
        violet_folder_id = get_or_create_violet_folder(service)
        log_msg("Carpeta 'Violet Uploads' lista en Drive")
        check_cancel()

        # Determinar carpeta ra\u00edz en Drive
        roots = set()
        for _, rp in file_list:
            root = rp.replace("\\", "/").split("/")[0]
            roots.add(root)

        single_file = total == 1 and "/" not in file_list[0][1] and not folder_name

        if single_file:
            drive_root_id = violet_folder_id
            display_name = file_list[0][1]
        else:
            if len(roots) == 1:
                root_name = folder_name or list(roots)[0]
            else:
                root_name = folder_name or "Subida"
            drive_root_id = create_drive_folder(root_name, parent_id=violet_folder_id, service=service)
            uploaded_ids.append(drive_root_id)
            display_name = root_name
            log_msg(f"Carpeta ra\u00edz creada en Drive: {root_name}")
        check_cancel()

        # Subir cada archivo
        for i, (dest, rp) in enumerate(file_list, 1):
            filename = os.path.basename(rp)
            pct = 5 + int((i / total) * 85)
            update(f"Subiendo archivo {i}/{total} \u2014 {filename}", pct)
            check_cancel()

            if len(roots) == 1:
                parts = rp.replace("\\", "/").split("/", 1)
                rel_path = parts[1] if len(parts) > 1 else ""
            else:
                rel_path = rp
            sub_dir = os.path.dirname(rel_path) if rel_path else ""
            if sub_dir:
                file_parent_id = ensure_drive_path(
                    sub_dir, drive_root_id, service=service,
                    cache=path_cache, track_ids=uploaded_ids
                )
            else:
                file_parent_id = drive_root_id
            check_cancel()

            if thumb_path is None:
                try:
                    if is_video_file(filename):
                        first_video_duration = get_video_duration(dest)
                        thumb_path = extract_thumbnail(dest)
                    elif is_image_file(filename):
                        thumb_path = extract_image_thumbnail(dest)
                except Exception:
                    pass

            file_id = upload_to_drive(dest, cancel_event, display_name=filename,
                                       folder_id=file_parent_id, service=service)
            uploaded_ids.append(file_id)

        check_cancel()
        log_msg("Archivos subidos a Drive correctamente")

        # Discord
        update("Enviando a Discord...", 95)
        log_msg("Enviando notificaci\u00f3n a Discord...")
        wh_url = os.getenv(f"DISCORD_WEBHOOK_{webhook_index}", "").strip()
        total_size = sum(os.path.getsize(d) for d, _ in file_list)

        if single_file:
            file_link = f"https://drive.google.com/file/d/{uploaded_ids[-1]}/view?usp=sharing"
            send_to_discord(
                link=file_link, webhook_url=wh_url,
                thumb_path=thumb_path, filename=display_name,
                duration=first_video_duration, total_size_bytes=total_size,
            )
        else:
            folder_link = f"https://drive.google.com/open?id={drive_root_id}"
            if len(roots) == 1:
                file_names = [os.path.basename(rp) for _, rp in file_list]
            else:
                seen = set()
                file_names = []
                for _, rp in file_list:
                    root = rp.replace("\\", "/").split("/")[0]
                    if root not in seen:
                        seen.add(root)
                        file_names.append(root)
            send_to_discord(
                link=folder_link, webhook_url=wh_url,
                thumb_path=thumb_path, folder_name=display_name,
                total_files=total, total_size_bytes=total_size,
                file_names=file_names,
            )

        log_msg("Notificaci\u00f3n enviada a Discord correctamente")
        _cleanup_task_dir(task_dir)
        update("Completado", 100, "done")

    except InterruptedError:
        update("Cancelado por el usuario", 0, "cancelled")
        if service is not None:
            for fid in reversed(uploaded_ids):
                try:
                    service.files().delete(fileId=fid).execute()
                except Exception:
                    pass
        _cleanup_task_dir(task_dir)
    except Exception as e:
        update(str(e), 0, "error")
        _cleanup_task_dir(task_dir)

@app.route('/api/upload/status/<task_id>')
def api_upload_status(task_id):
    with upload_tasks_lock:
        task = upload_tasks.get(task_id)
        if task is None:
            return jsonify({"state": "not_found"})
        return jsonify({
            "state": task["state"],
            "message": task["message"],
            "progress": task["progress"],
            "filename": task["filename"],
            "total_files": task.get("total_files", 1),
            "log": task.get("log", []),
        })

@app.route('/api/upload/cancel/<task_id>', methods=['POST'])
def api_upload_cancel(task_id):
    with upload_tasks_lock:
        task = upload_tasks.get(task_id)
        if task and task["state"] == "uploading":
            task["cancel_event"].set()
            return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "No se encontr\u00f3 la tarea o ya finaliz\u00f3."})


# ── Shutdown ──

@app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    os._exit(0)


# ── Utils ──

def _cleanup_task_dir(task_dir):
    try:
        for root, dirs, files in os.walk(task_dir, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except Exception:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except Exception:
                    pass
        os.rmdir(task_dir)
    except Exception:
        pass


def find_free_port(start=5000):
    for port in range(start, start + 100):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue
    return start


# ── Main ──

if __name__ == '__main__':
    port = find_free_port(5000)
    try:
        import webview
        threading.Thread(target=lambda: app.run(host='127.0.0.1', port=port, debug=False, threaded=True), daemon=True).start()
        time.sleep(1.5)
        webview.create_window("Violet Uploader", f"http://localhost:{port}", width=1100, height=700)
        webview.start()
        os._exit(0)
    except ImportError:
        webbrowser.open(f'http://localhost:{port}')
        app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
