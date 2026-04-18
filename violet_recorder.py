import obsws_python as obs
import requests
import os
import pickle
import tkinter as tk
from tkinter import scrolledtext, ttk
from datetime import datetime
import threading
import winsound
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv, set_key

# ── CONFIGURACION DE RUTAS ────────────────────────────────
ENV_PATH   = os.path.abspath(".env")
CONFIG_DIR = os.path.abspath("config")
CREDS_JSON = os.path.join(CONFIG_DIR, "credentials.json")
TOKEN_PICKLE = os.path.join(CONFIG_DIR, "token.pickle")

if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

load_dotenv(ENV_PATH)

# ── PALETA (Discord dark + acento Violet) ─────────────────
BG_BASE    = "#313338"
BG_CARD    = "#2B2D31"
BG_INPUT   = "#1E1F22"
BG_SIDEBAR = "#2B2D31"
ACCENT     = "#7C3AED"
ACCENT_LT  = "#9D6FF0"
FG_WHITE   = "#FFFFFF"
FG_MAIN    = "#DCDDDE"
FG_MUTED   = "#96989D"
FG_OK      = "#57F287"
FG_WARN    = "#FEE75C"
FG_ERR     = "#ED4245"
FG_INFO    = "#5865F2"
DIVIDER    = "#3F4147"

FONT_UI    = ("Segoe UI", 9)
FONT_BOLD  = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 11, "bold")
FONT_MONO  = ("Consolas", 9)
FONT_SMALL = ("Segoe UI", 8)

STATUS_MAP = {
    "ok":    (FG_OK,   "Conectado"),
    "warn":  (FG_WARN, "Grabando"),
    "error": (FG_ERR,  "Error de conexion"),
    "info":  (FG_INFO, "Conectando..."),
}

# ── UTILIDADES ───────────────────────────────────────────
def play_notification_sound():
    try:
        winsound.MessageBeep(winsound.MB_OK)
    except:
        pass

def format_size(path):
    try:
        b = os.path.getsize(path) if os.path.exists(path) else 0
        if b >= 1_073_741_824: return f"{b/1_073_741_824:.2f} GB"
        if b >= 1_048_576:     return f"{b/1_048_576:.2f} MB"
        if b > 0:              return f"{b/1024:.1f} KB"
    except:
        pass
    return "N/A"

# ── GOOGLE DRIVE ──────────────────────────────────────────
def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_JSON):
                raise FileNotFoundError("Falta credentials.json en carpeta config")
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDS_JSON, ["https://www.googleapis.com/auth/drive.file"])
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PICKLE, "wb") as f:
            pickle.dump(creds, f)
    return build("drive", "v3", credentials=creds)

def upload_to_drive(filepath):
    service = get_drive_service()
    media   = MediaFileUpload(filepath, resumable=True)
    request = service.files().create(
        body={"name": os.path.basename(filepath)},
        media_body=media, fields="id")
    response = None
    while response is None:
        _, response = request.next_chunk()
    file_id = response.get("id")
    service.permissions().create(
        fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://drive.google.com/file/d/{file_id}/view"

# ── DISCORD ───────────────────────────────────────────────
def send_to_discord(link, filepath, duration_str):
    webhook_url = os.getenv("DISCORD_WEBHOOK")
    if not webhook_url:
        return False
    now      = datetime.now()
    size_str = format_size(filepath)
    payload  = {
        "username":   "Violet Recorder",
        "avatar_url": "https://i.imgur.com/QTWoeUF.png",
        "embeds": [{
            "title":       "📼 Grabación Disponible",   
            "description": f"**[Abrir en Google Drive]({link})**",
            "color":       0x7C3AED,
            "fields": [
                {"name": "Archivo",  "value": f"`{os.path.basename(filepath)}`", "inline": True},
                {"name": "Duración", "value": f"`{duration_str}`",               "inline": True},
                {"name": "Tamaño",  "value": f"`{size_str}`",                   "inline": True},
                {"name": "Fecha",    "value": now.strftime("%d/%m/%Y"),           "inline": True},
                {"name": "Hora", "value": now.strftime("%I:%M %p").replace("AM", "a.m.").replace("PM", "p.m."), "inline": True},
            ],
            "footer":    {"text": "Violet Recorder v1.0"},
        }]
    }
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code in [200, 204]:
            play_notification_sound()
            return True
    except:
        pass
    return False

# ── MANEJADOR DE EVENTOS OBS ──────────────────────────────
class RecordingHandler:
    def __init__(self, app):
        self.app = app

    def on_record_state_changed(self, data):
        state = data.output_state
        if state == "OBS_WEBSOCKET_OUTPUT_STARTED":
            self.app._start_time = datetime.now()
            self.app.after(0, self.app.add_log, "Grabación iniciada.", "warn")
            self.app.after(0, self.app.set_status, "warn")
        elif state == "OBS_WEBSOCKET_OUTPUT_STOPPED":
            filepath = getattr(data, "output_path", None) or getattr(data, "return_code", None)
            if filepath and os.path.exists(filepath):
                duration = str(datetime.now() - self.app._start_time).split(".")[0] \
                           if self.app._start_time else "N/A"
                self.app.after(0, self.app.add_log,
                               f"Grabación finalizada ({duration}).", "info")
                threading.Thread(
                    target=self.process_upload,
                    args=(filepath, duration), daemon=True).start()

    def process_upload(self, filepath, duration):
        try:
            self.app.after(0, self.app.set_status, "info")
            self.app.after(0, self.app.add_log,
                           "Subiendo archivo a Google Drive...", "info")
            link = upload_to_drive(filepath)
            self.app.after(0, self.app.add_log,
                           "Archivo subido correctamente.", "ok")

            self.app.after(0, self.app.add_log,
                           "Enviando notificación a Discord...", "info")
            if send_to_discord(link, filepath, duration):
                self.app.after(0, self.app.add_log,
                               "Notificación enviada a Discord.", "ok")
            else:
                self.app.after(0, self.app.add_log,
                               "No se pudo enviar la notificación a Discord.", "warn")

            self.app.after(0, self.app.set_status, "ok")
        except Exception as e:
            self.app.after(0, self.app.add_log, f"Error: {e}", "error")
            self.app.after(0, self.app.set_status, "error")

# ── APP PRINCIPAL ─────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Violet Recorder")
        self.geometry("580x500")
        self.minsize(480, 380)
        self.configure(bg=BG_BASE)
        self.iconbitmap("icono.ico")
        self._start_time = None
        self._build_ui()
        self.after(100, self._connect_obs)

    def _build_ui(self):
        # Topbar
        topbar = tk.Frame(self, bg=BG_CARD, height=46)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="Violet Recorder", bg=BG_CARD,
                 fg=FG_WHITE, font=FONT_TITLE).pack(side="left", padx=14, pady=10)

        ver_lbl = tk.Label(topbar, text=" v1.0 ", bg=ACCENT, fg=FG_WHITE,
                           font=FONT_SMALL, padx=4)
        ver_lbl.pack(side="left", pady=14)

        cfg_btn = tk.Button(topbar, text="Configuración",
                            bg=ACCENT, fg=FG_WHITE,
                            activebackground=ACCENT_LT, activeforeground=FG_WHITE,
                            relief="flat", font=FONT_BOLD,
                            padx=14, pady=5, cursor="hand2",
                            command=self.open_settings)
        cfg_btn.pack(side="right", padx=12, pady=8)

        tk.Frame(self, bg=DIVIDER, height=1).pack(fill="x")

        # Tarjeta de estado
        status_card = tk.Frame(self, bg=BG_CARD, padx=14, pady=10)
        status_card.pack(fill="x", padx=12, pady=(12, 0))

        tk.Label(status_card, text="OBS WEBSOCKET",
                 bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")

        row = tk.Frame(status_card, bg=BG_CARD)
        row.pack(fill="x", pady=(4, 0))

        self._dot = tk.Canvas(row, width=10, height=10,
                              bg=BG_CARD, highlightthickness=0)
        self._dot.pack(side="left", pady=1)
        self._dot_id = self._dot.create_oval(1, 1, 9, 9,
                                             fill=FG_ERR, outline="")

        self.status_label = tk.Label(row, text="Desconectado",
                                     bg=BG_CARD, fg=FG_ERR, font=FONT_BOLD)
        self.status_label.pack(side="left", padx=8)

        # Tarjeta de log
        log_card = tk.Frame(self, bg=BG_CARD)
        log_card.pack(fill="both", expand=True, padx=12, pady=12)

        log_header = tk.Frame(log_card, bg=BG_CARD, padx=14, pady=8)
        log_header.pack(fill="x")
        tk.Label(log_header, text="REGISTRO DE ACTIVIDAD",
                 bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")

        tk.Frame(log_card, bg=DIVIDER, height=1).pack(fill="x")

        self.log_area = scrolledtext.ScrolledText(
            log_card, bg=BG_CARD, fg=FG_MAIN, font=FONT_MONO,
            relief="flat", bd=0, padx=14, pady=10,
            selectbackground=ACCENT, selectforeground=FG_WHITE,
            insertbackground=FG_WHITE
        )
        self.log_area.pack(fill="both", expand=True)
        self.log_area.tag_config("info",  foreground=FG_INFO)
        self.log_area.tag_config("ok",    foreground=FG_OK)
        self.log_area.tag_config("warn",  foreground=FG_WARN)
        self.log_area.tag_config("error", foreground=FG_ERR)
        self.log_area.tag_config("muted", foreground=FG_MUTED)

        # Footer
        footer = tk.Frame(self, bg=BG_SIDEBAR, height=24)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(footer, text="Violet Recorder  |  Google Drive Upload",
                 bg=BG_SIDEBAR, fg=FG_MUTED, font=FONT_SMALL).pack(
                 side="left", padx=12, pady=4)

    def set_status(self, level="info"):
        dot_color   = {"ok": FG_OK, "warn": FG_WARN,
                       "error": FG_ERR, "info": FG_INFO}.get(level, FG_MUTED)
        text_color, label = STATUS_MAP.get(level, (FG_MUTED, "..."))
        self._dot.itemconfig(self._dot_id, fill=dot_color)
        self.status_label.config(text=label, fg=text_color)

    def add_log(self, message, tag="info"):
        ts     = datetime.now().strftime("%H:%M:%S")
        prefix = {"info": "INFO", "ok": "OK  ", "warn": "WARN",
                  "error": "ERR "}.get(tag, "    ")
        self.log_area.insert(tk.END, f"[{ts}]  ", "muted")
        self.log_area.insert(tk.END, f"{prefix}  ", tag)
        self.log_area.insert(tk.END, f"{message}\n")
        self.log_area.see(tk.END)

    def open_settings(self):
        SettingsWindow(self)

    def _connect_obs(self):
        def connect():
            try:
                self.obs_client = obs.EventClient(
                    host=os.getenv("OBS_HOST", "localhost"),
                    port=int(os.getenv("OBS_PORT", "4455")),
                    password=os.getenv("OBS_PASSWORD", "")
                )
                self.obs_client.callback.register(
                    RecordingHandler(self).on_record_state_changed)
                self.after(0, self.set_status, "ok")
                self.after(0, self.add_log,
                           "Enlace con OBS establecido correctamente.", "ok")
            except Exception as e:
                self.after(0, self.set_status, "error")
                self.after(0, self.add_log,
                           f"No se pudo conectar con OBS: {e}", "error")
        threading.Thread(target=connect, daemon=True).start()


# ── VENTANA DE CONFIGURACION ──────────────────────────────
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Configuración - Violet Recorder")
        self.geometry("440x440")
        self.configure(bg=BG_BASE)
        self.iconbitmap("icono.ico")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        # Topbar
        topbar = tk.Frame(self, bg=BG_CARD, height=40)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text="Configuración", bg=BG_CARD,
                 fg=FG_WHITE, font=FONT_BOLD).pack(side="left", padx=14, pady=8)

        tk.Frame(self, bg=DIVIDER, height=1).pack(fill="x")

        # Campos
        body = tk.Frame(self, bg=BG_BASE, padx=18, pady=14)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="PARÁMETROS DE CONEXIÓN",
                 bg=BG_BASE, fg=FG_MUTED, font=FONT_SMALL).pack(
                 anchor="w", pady=(0, 10))

        self.vars = {
            "OBS_HOST":        tk.StringVar(value=os.getenv("OBS_HOST",        "localhost")),
            "OBS_PORT":        tk.StringVar(value=os.getenv("OBS_PORT",        "4455")),
            "OBS_PASSWORD":    tk.StringVar(value=os.getenv("OBS_PASSWORD",    "")),
            "DISCORD_WEBHOOK": tk.StringVar(value=os.getenv("DISCORD_WEBHOOK", ""))
        }
        labels = {
            "OBS_HOST":        "Host OBS",
            "OBS_PORT":        "Puerto OBS",
            "OBS_PASSWORD":    "Contraseña OBS",
            "DISCORD_WEBHOOK": "Discord Webhook URL"
        }

        for key, var in self.vars.items():
            grp = tk.Frame(body, bg=BG_BASE)
            grp.pack(fill="x", pady=5)
            tk.Label(grp, text=labels[key].upper(),
                     bg=BG_BASE, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
            show = "*" if "PASSWORD" in key else ""
            tk.Entry(grp, textvariable=var, font=FONT_MONO,
                     bg=BG_INPUT, fg=FG_WHITE, relief="flat",
                     insertbackground=FG_WHITE, show=show,
                     selectbackground=ACCENT).pack(
                     fill="x", ipady=6, pady=(3, 0))

        # Botones
        tk.Frame(self, bg=DIVIDER, height=1).pack(fill="x")
        btn_row = tk.Frame(self, bg=BG_CARD, padx=14, pady=10)
        btn_row.pack(fill="x")

        tk.Button(btn_row, text="Guardar", font=FONT_BOLD,
                  bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_LT,
                  activeforeground=FG_WHITE, relief="flat",
                  padx=18, pady=5, cursor="hand2",
                  command=self._save).pack(side="right", padx=(8, 0))

        tk.Button(btn_row, text="Cancelar", font=FONT_UI,
                  bg=BG_INPUT, fg=FG_MUTED, activebackground=DIVIDER,
                  activeforeground=FG_WHITE, relief="flat",
                  padx=18, pady=5, cursor="hand2",
                  command=self.destroy).pack(side="right")

    def _save(self):
        for key, var in self.vars.items():
            set_key(ENV_PATH, key, var.get())
        self._show_success("Cambios guardados. Reinicia la aplicación para aplicarlos.")

    def _show_success(self, message):
        lbl = tk.Label(self, text=f"✓  {message}", bg=BG_CARD,
                       fg=FG_OK, font=FONT_SMALL, anchor="w", padx=14)
        lbl.pack(fill="x", side="bottom", pady=(0, 4))
        self.after(4000, lbl.destroy)


if __name__ == "__main__":
    app = App()
    app.mainloop()