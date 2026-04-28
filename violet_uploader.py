# ═════════════════════════════════════════════════════════════
# VIOLET UPLOADER
# Aplicación de escritorio para subir videos a Google Drive
# y enviar notificaciones a Discord con miniatura del video.
# ═════════════════════════════════════════════════════════════
import os
import pickle
import requests
import tkinter as tk
from tkinter import scrolledtext, ttk, filedialog, messagebox
from datetime import datetime
import threading
import winsound
import cv2
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv, set_key

# ── RUTAS DE ARCHIVOS ───────────────────────────────────────────
ENV_PATH     = os.path.abspath(".env")
CONFIG_DIR   = os.path.abspath("config")
CREDS_JSON   = os.path.join(CONFIG_DIR, "credentials.json")
TOKEN_PICKLE = os.path.join(CONFIG_DIR, "token.pickle")

if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

load_dotenv(ENV_PATH)

# ── PALETA DE COLORES (Discord-style) ────────────────────────────────
BG_BASE    = "#313338"
BG_CARD    = "#2B2D31"
BG_INPUT   = "#1E1F22"
BG_SIDEBAR = "#2B2D31"
BG_SELECT  = "#383A40"
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
    "ok":     (FG_OK,   "Completado"),
    "upload": (FG_WARN, "Subiendo..."),
    "error":  (FG_ERR,  "Error"),
    "info":   (FG_INFO, "Procesando..."),
    "idle":   (FG_MUTED,"Sin actividad"),
    "cancel": (FG_ERR,  "Cancelado"),
}

# ── UTILIDADES ────────────────────────────────────────────
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

def is_logged_in():
    """Comprueba si existe un token de Drive válido o renovable."""
    if not os.path.exists(TOKEN_PICKLE):
        return False
    try:
        with open(TOKEN_PICKLE, "rb") as f:
            creds = pickle.load(f)
        return bool(creds and (creds.valid or (creds.expired and creds.refresh_token)))
    except:
        return False

def get_google_account_email():
    """Devuelve el email de la cuenta autenticada, o None."""
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
    except:
        return None

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
                raise FileNotFoundError(
                    "Falta credentials.json en la carpeta config/.\n"
                    "Descárgalo desde Google Cloud Console y colócalo en config/.")
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDS_JSON,
                ["https://www.googleapis.com/auth/drive.file",
                 "https://www.googleapis.com/auth/userinfo.email",
                 "openid"])
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PICKLE, "wb") as f:
            pickle.dump(creds, f)
    return build("drive", "v3", credentials=creds)

def upload_to_drive(filepath, cancel_event):
    service = get_drive_service()
    media   = MediaFileUpload(filepath, resumable=True)
    request = service.files().create(
        body={"name": os.path.basename(filepath)},
        media_body=media, fields="id")
    response = None
    while response is None:
        if cancel_event.is_set():
            raise InterruptedError("Subida cancelada por el usuario.")
        _, response = request.next_chunk()
    file_id = response.get("id")
    service.permissions().create(
        fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
    return file_id

# ── THUMBNAIL ─────────────────────────────────────────────
def extract_thumbnail(filepath):
    cap   = cv2.VideoCapture(filepath)
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

def upload_thumbnail_to_drive(thumb_path):
    service = get_drive_service()
    media   = MediaFileUpload(thumb_path, mimetype="image/jpeg")
    result  = service.files().create(
        body={"name": os.path.basename(thumb_path)},
        media_body=media, fields="id").execute()
    file_id = result.get("id")
    service.permissions().create(
        fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://drive.google.com/uc?id={file_id}"

# ── DISCORD ───────────────────────────────────────────────
def send_to_discord(link, filepath, duration_str, thumb_url, webhook_url):
    now      = datetime.now()
    size_str = format_size(filepath)
    embed = {
        "title":       "📼 Grabación Disponible",
        "description": f"**[Abrir en Google Drive]({link})**",
        "color":       0x7C3AED,
        "fields": [
            {"name": "Archivo",  "value": f"`{os.path.basename(filepath)}`", "inline": True},
            {"name": "Duración", "value": f"`{duration_str}`",               "inline": True},
            {"name": "Tamaño",   "value": f"`{size_str}`",                   "inline": True},
            {"name": "Fecha",    "value": now.strftime("%d/%m/%Y"),           "inline": True},
            {"name": "Hora",     "value": now.strftime("%I:%M %p")
                                          .replace("AM","a.m.").replace("PM","p.m."), "inline": True},
        ],
        "footer": {"text": "Si Google Drive no ha terminado de procesar el video, "
                           "puedes descargarlo de todas formas.\n\nViolet Uploader v1.2"},
    }
    if thumb_url:
        embed["image"] = {"url": thumb_url}
    payload = {
        "username":   "Violet Uploader",
        "avatar_url": "https://i.imgur.com/QTWoeUF.png",
        "embeds":     [embed],
    }
    r = requests.post(webhook_url, json=payload, timeout=10)
    if r.status_code not in (200, 204):
        raise ConnectionError(f"Discord respondió con código {r.status_code}.")
    play_notification_sound()
    return True


# ══════════════════════════════════════════════════════════
# DIÁLOGO ESTILIZADO (reemplaza messagebox estándar)
# ══════════════════════════════════════════════════════════
class StyledDialog(tk.Toplevel):
    """Diálogo modal con la estética de la app."""

    def __init__(self, parent, title, message, kind="info",
                 btn_ok="Aceptar", btn_cancel=None):
        super().__init__(parent)
        self.result = False
        self.title(title)
        self.configure(bg=BG_BASE)
        self.resizable(False, False)
        self.grab_set()
        try:
            self.iconbitmap("icono.ico")
        except:
            pass

        icon_map = {"info": ("ℹ", FG_INFO), "ok": ("✓", FG_OK),
                    "warn": ("⚠", FG_WARN), "error": ("✕", FG_ERR),
                    "question": ("?", ACCENT)}
        icon_char, icon_color = icon_map.get(kind, ("ℹ", FG_INFO))

        # Topbar
        topbar = tk.Frame(self, bg=BG_CARD, height=44)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text=title, bg=BG_CARD, fg=FG_WHITE,
                 font=FONT_TITLE).pack(side="left", padx=14)
        tk.Frame(self, bg=DIVIDER, height=1).pack(fill="x")

        # Cuerpo
        body = tk.Frame(self, bg=BG_BASE, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        icon_lbl = tk.Label(body, text=icon_char, bg=BG_BASE,
                            fg=icon_color, font=("Segoe UI", 22, "bold"))
        icon_lbl.pack(pady=(4, 10))

        tk.Label(body, text=message, bg=BG_BASE, fg=FG_MAIN,
                 font=FONT_UI, wraplength=340, justify="center").pack()

        # Botones
        tk.Frame(self, bg=DIVIDER, height=1).pack(fill="x")
        btn_row = tk.Frame(self, bg=BG_CARD, padx=14, pady=10)
        btn_row.pack(fill="x")

        if btn_cancel:
            tk.Button(btn_row, text=btn_cancel, font=FONT_UI,
                      bg=BG_INPUT, fg=FG_MUTED, activebackground=DIVIDER,
                      activeforeground=FG_WHITE, relief="flat",
                      padx=18, pady=5, cursor="hand2",
                      command=self._cancel).pack(side="right", padx=(6, 0))

        tk.Button(btn_row, text=btn_ok, font=FONT_BOLD,
                  bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_LT,
                  activeforeground=FG_WHITE, relief="flat",
                  padx=18, pady=5, cursor="hand2",
                  command=self._ok).pack(side="right")

        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        px = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"+{px}+{py}")
        self.wait_window()

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


def styled_info(parent, title, message):
    StyledDialog(parent, title, message, kind="info")

def styled_warn(parent, title, message):
    StyledDialog(parent, title, message, kind="warn")

def styled_error(parent, title, message):
    StyledDialog(parent, title, message, kind="error")

def styled_ask(parent, title, message):
    d = StyledDialog(parent, title, message, kind="question",
                     btn_ok="Sí, subir", btn_cancel="Cancelar")
    return d.result


# ══════════════════════════════════════════════════════════
# SELECTOR DE WEBHOOK (dropdown estilizado)
# ══════════════════════════════════════════════════════════
class WebhookSelector(tk.Frame):
    """Desplegable que lista los webhooks configurados."""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG_CARD, **kw)
        self._popup   = None
        self._choice  = tk.StringVar(value="")   # índice elegido como str
        self._build()

    def _build(self):
        tk.Label(self, text="CANAL / WEBHOOK DESTINO", bg=BG_CARD,
                 fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")

        row = tk.Frame(self, bg=BG_CARD)
        row.pack(fill="x", pady=(4, 0))

        self._display = tk.Label(row, text="— Selecciona un webhook —",
                                 bg=BG_INPUT, fg=FG_MUTED, font=FONT_UI,
                                 anchor="w", padx=10, pady=7,
                                 relief="flat", cursor="hand2")
        self._display.pack(side="left", fill="x", expand=True, ipady=1)

        self._arrow = tk.Label(row, text="▾", bg=ACCENT, fg=FG_WHITE,
                               font=FONT_BOLD, padx=10, pady=6,
                               cursor="hand2")
        self._arrow.pack(side="left")

        self._display.bind("<Button-1>", lambda _: self._toggle())
        self._arrow.bind("<Button-1>",   lambda _: self._toggle())

    def _toggle(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        self._open_popup()

    def _open_popup(self):
        hooks = self._get_hooks()
        if not hooks:
            return

        self._popup = tk.Toplevel(self)
        self._popup.overrideredirect(True)
        self._popup.configure(bg=DIVIDER)

        self.update_idletasks()
        x = self._display.winfo_rootx()
        y = self._display.winfo_rooty() + self._display.winfo_height() + 2
        w = self._display.winfo_width() + self._arrow.winfo_width()
        self._popup.geometry(f"{w}x{min(len(hooks)*44, 220)}+{x}+{y}")

        scroll_wrap = tk.Frame(self._popup, bg=BG_INPUT)
        scroll_wrap.pack(fill="both", expand=True, padx=1, pady=1)

        canvas = tk.Canvas(scroll_wrap, bg=BG_INPUT, highlightthickness=0)
        sb     = ttk.Scrollbar(scroll_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        if len(hooks) > 5:
            sb.pack(side="right", fill="y")

        inner = tk.Frame(canvas, bg=BG_INPUT)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        for idx, name in hooks:
            item = tk.Frame(inner, bg=BG_INPUT, cursor="hand2")
            item.pack(fill="x")
            dot = tk.Canvas(item, width=8, height=8,
                            bg=BG_INPUT, highlightthickness=0)
            dot.pack(side="left", padx=(10, 6), pady=10)
            dot.create_oval(1, 1, 7, 7, fill=FG_OK, outline="")
            lbl = tk.Label(item, text=name, bg=BG_INPUT, fg=FG_MAIN,
                           font=FONT_UI, anchor="w", padx=4)
            lbl.pack(side="left", fill="x", expand=True, ipady=2)

            def _select(i=idx, n=name):
                self._choice.set(str(i))
                self._display.config(text=f"# {n}", fg=FG_WHITE)
                if self._popup:
                    self._popup.destroy()
                    self._popup = None

            item.bind("<Button-1>", lambda _, s=_select: s())
            lbl.bind("<Button-1>",  lambda _, s=_select: s())
            dot.bind("<Button-1>",  lambda _, s=_select: s())

            # Hover
            for w in (item, lbl, dot):
                w.bind("<Enter>", lambda _, f=item: f.config(bg=BG_SELECT))
                w.bind("<Leave>", lambda _, f=item, d=dot, l=lbl:
                       (f.config(bg=BG_INPUT), d.config(bg=BG_INPUT),
                        l.config(bg=BG_INPUT)))

        self._popup.bind("<FocusOut>", lambda _: self._popup.destroy()
                         if self._popup and self._popup.winfo_exists() else None)
        self._popup.focus_set()

    def _get_hooks(self):
        result = []
        for i in range(5):
            name = os.getenv(f"DISCORD_WEBHOOK_NAME_{i}", "").strip()
            url  = os.getenv(f"DISCORD_WEBHOOK_{i}",      "").strip()
            if name and url:
                result.append((i, name))
        return result

    def get_selected(self):
        """Devuelve (index, name, url) o (None, None, None)."""
        val = self._choice.get()
        if not val:
            return None, None, None
        idx  = int(val)
        name = os.getenv(f"DISCORD_WEBHOOK_NAME_{idx}", f"Webhook #{idx+1}")
        url  = os.getenv(f"DISCORD_WEBHOOK_{idx}", "").strip()
        return idx, name, url

    def refresh(self):
        """Refresca la selección si el webhook elegido ya no existe."""
        val = self._choice.get()
        if val:
            idx = int(val)
            url  = os.getenv(f"DISCORD_WEBHOOK_{idx}", "").strip()
            name = os.getenv(f"DISCORD_WEBHOOK_NAME_{idx}", "").strip()
            if url and name:
                self._display.config(text=f"# {name}", fg=FG_WHITE)
                return
        self._choice.set("")
        self._display.config(text="— Selecciona un webhook —", fg=FG_MUTED)


# ══════════════════════════════════════════════════════════
# APLICACIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Violet Uploader")
        self.geometry("520x700")
        self.configure(bg=BG_BASE)
        try:
            self.iconbitmap("icono.ico")
        except:
            pass
        self.resizable(False, False)

        self.uploading     = False
        self._cancel_event = threading.Event()
        self._selected_file = None   # ruta del video elegido

        self._build_ui()
        self.set_status("idle")

    # ── UI ────────────────────────────────────────────────
    def _build_ui(self):
        # Topbar
        topbar = tk.Frame(self, bg=BG_CARD, height=44)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text="Violet Uploader",
                 bg=BG_CARD, fg=FG_WHITE, font=FONT_TITLE).pack(side="left", padx=14)
        tk.Button(topbar, text="⚙  Configuración",
                  bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_LT,
                  activeforeground=FG_WHITE, relief="flat", font=FONT_BOLD,
                  padx=14, pady=4, cursor="hand2",
                  command=self.open_settings).pack(side="right", padx=12, pady=8)
        tk.Frame(self, bg=DIVIDER, height=1).pack(fill="x")

        # ── Tarjeta de estado ─────────────────────────────
        s_card = tk.Frame(self, bg=BG_CARD, padx=14, pady=10)
        s_card.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(s_card, text="ESTADO", bg=BG_CARD,
                 fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        s_row = tk.Frame(s_card, bg=BG_CARD)
        s_row.pack(fill="x", pady=(6, 0))
        self._dot    = tk.Canvas(s_row, width=10, height=10,
                                 bg=BG_CARD, highlightthickness=0)
        self._dot.pack(side="left")
        self._dot_id = self._dot.create_oval(1, 1, 9, 9, fill=FG_MUTED, outline="")
        self.status_label = tk.Label(s_row, text="Sin actividad",
                                     bg=BG_CARD, fg=FG_MUTED, font=FONT_BOLD)
        self.status_label.pack(side="left", padx=8)

        # ── Tarjeta: selección de video ───────────────────
        v_card = tk.Frame(self, bg=BG_CARD, padx=14, pady=12)
        v_card.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(v_card, text="ARCHIVO DE VIDEO", bg=BG_CARD,
                 fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w", pady=(0, 6))

        file_row = tk.Frame(v_card, bg=BG_CARD)
        file_row.pack(fill="x")

        self._file_label = tk.Label(file_row, text="Ningún archivo seleccionado",
                                    bg=BG_INPUT, fg=FG_MUTED, font=FONT_MONO,
                                    anchor="w", padx=10, pady=6, wraplength=340)
        self._file_label.pack(side="left", fill="x", expand=True)

        tk.Button(file_row, text="📂  Examinar",
                  bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_LT,
                  activeforeground=FG_WHITE, relief="flat", font=FONT_BOLD,
                  padx=10, pady=4, cursor="hand2",
                  command=self._browse_file).pack(side="left", padx=(8, 0))

        # ── Tarjeta: selector de webhook ──────────────────
        w_card = tk.Frame(self, bg=BG_CARD, padx=14, pady=12)
        w_card.pack(fill="x", padx=12, pady=(10, 0))
        self._webhook_selector = WebhookSelector(w_card)
        self._webhook_selector.pack(fill="x")

        # ── Tarjeta: botones de acción ────────────────────
        a_card = tk.Frame(self, bg=BG_CARD, padx=14, pady=12)
        a_card.pack(fill="x", padx=12, pady=(10, 0))

        btn_row = tk.Frame(a_card, bg=BG_CARD)
        btn_row.pack(fill="x")

        self.upload_btn = tk.Button(btn_row, text="📤  Subir video",
                  bg=FG_OK, fg="#000000", activebackground="#45C46A",
                  activeforeground="#000000", relief="flat", font=FONT_BOLD,
                  padx=14, pady=6, cursor="hand2",
                  command=self._start_upload)
        self.upload_btn.pack(side="left", padx=(0, 8))

        self.cancel_btn = tk.Button(btn_row, text="✕  Cancelar subida",
                  bg=FG_ERR, fg=FG_WHITE, activebackground="#C43235",
                  activeforeground=FG_WHITE, relief="flat", font=FONT_BOLD,
                  padx=14, pady=6, cursor="hand2", state="disabled",
                  command=self.cancel_upload)
        self.cancel_btn.pack(side="left")

        # Barra de progreso (oculta por defecto)
        self._progress_frame = tk.Frame(a_card, bg=BG_CARD)
        self._progress_bar = ttk.Progressbar(
            self._progress_frame, mode="indeterminate", length=460)

        # ── Tarjeta de log ────────────────────────────────
        log_card = tk.Frame(self, bg=BG_CARD)
        log_card.pack(fill="both", expand=True, padx=12, pady=(10, 12))
        log_hdr = tk.Frame(log_card, bg=BG_CARD, padx=14, pady=8)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text="REGISTRO DE ACTIVIDAD",
                 bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        tk.Frame(log_card, bg=DIVIDER, height=1).pack(fill="x")
        self.log_area = scrolledtext.ScrolledText(
            log_card, bg=BG_CARD, fg=FG_MAIN, font=FONT_MONO,
            relief="flat", bd=0, padx=14, pady=10,
            selectbackground=ACCENT, selectforeground=FG_WHITE,
            insertbackground=FG_WHITE)
        self.log_area.pack(fill="both", expand=True)
        for tag, fg in [("info", FG_INFO), ("ok", FG_OK), ("warn", FG_WARN),
                        ("error", FG_ERR), ("muted", FG_MUTED)]:
            self.log_area.tag_config(tag, foreground=fg)

        # Footer
        footer = tk.Frame(self, bg=BG_SIDEBAR, height=24)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(footer, text="Violet Uploader v1.+2  |  Google Drive + Discord",
                 bg=BG_SIDEBAR, fg=FG_MUTED, font=FONT_SMALL).pack(
                 side="left", padx=12, pady=4)

    # ── ESTADO / LOG ──────────────────────────────────────
    def set_status(self, level="idle"):
        dot_colors = {"ok": FG_OK, "upload": FG_WARN, "error": FG_ERR,
                      "info": FG_INFO, "idle": FG_MUTED, "cancel": FG_ERR}
        fg, label  = STATUS_MAP.get(level, (FG_MUTED, "Sin actividad"))
        self._dot.itemconfig(self._dot_id, fill=dot_colors.get(level, FG_MUTED))
        self.status_label.config(text=label, fg=fg)

    def add_log(self, message, tag="info"):
        ts     = datetime.now().strftime("%H:%M:%S")
        prefix = {"info":"INFO","ok":"OK  ","warn":"WARN","error":"ERR "}.get(tag,"    ")
        self.log_area.insert(tk.END, f"[{ts}]  ", "muted")
        self.log_area.insert(tk.END, f"{prefix}  ", tag)
        self.log_area.insert(tk.END, f"{message}\n")
        self.log_area.see(tk.END)

    def update_last_log(self, message, tag="info"):
        ts     = datetime.now().strftime("%H:%M:%S")
        prefix = {"info":"INFO","ok":"OK  ","warn":"WARN","error":"ERR "}.get(tag,"    ")
        self.log_area.delete("end-2l", "end-1l")
        self.log_area.insert(tk.END, f"[{ts}]  ", "muted")
        self.log_area.insert(tk.END, f"{prefix}  ", tag)
        self.log_area.insert(tk.END, f"{message}\n")
        self.log_area.see(tk.END)

    # ── SELECCIÓN DE ARCHIVO ──────────────────────────────
    def _browse_file(self):
        if self.uploading:
            styled_warn(self, "Subida en curso",
                        "No puedes cambiar el archivo mientras hay una subida activa.")
            return

        filepath = filedialog.askopenfilename(
            title="Selecciona un video para subir",
            filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov *.webm"), ("Todos", "*.*")])

        if not filepath:
            return
        if not os.path.exists(filepath):
            styled_error(self, "Archivo no encontrado",
                         "El archivo seleccionado no existe o no es accesible.")
            return

        self._selected_file = filepath
        short = os.path.basename(filepath)
        size  = format_size(filepath)
        self._file_label.config(
            text=f"{short}  ({size})", fg=FG_WHITE)
        self.add_log(f"Archivo seleccionado: {short}  [{size}]", "info")

    # ── VALIDACIONES ──────────────────────────────────────
    def _validate_pre_upload(self):
        """Devuelve (webhook_url, webhook_name, error_msg)."""

        # 1. ¿Hay sesión iniciada?
        if not is_logged_in():
            return None, None, (
                "No has iniciado sesión con Google Drive.\n\n"
                "Ve a Configuración → Google Drive e inicia sesión.")

        # 2. ¿Hay archivo seleccionado?
        if not self._selected_file:
            return None, None, (
                "No has seleccionado ningún archivo.\n\n"
                "Usa el botón «Examinar» para elegir un video.")

        # 3. ¿El archivo sigue existiendo?
        if not os.path.exists(self._selected_file):
            return None, None, (
                "El archivo seleccionado ya no existe en el disco.\n\n"
                "Por favor elige otro video.")

        # 4. ¿Ya hay una subida activa?
        if self.uploading:
            return None, None, (
                "Ya hay una subida en curso.\n\n"
                "Espera a que finalice o cancélala antes de iniciar una nueva.")

        # 5. ¿Hay webhooks configurados?
        has_any = any(
            os.getenv(f"DISCORD_WEBHOOK_{i}", "").strip()
            for i in range(5))
        if not has_any:
            return None, None, (
                "No hay ningún webhook de Discord configurado.\n\n"
                "Ve a Configuración → Webhooks y añade al menos uno.")

        # 6. ¿Se ha elegido webhook en el selector?
        idx, name, url = self._webhook_selector.get_selected()
        if idx is None:
            return None, None, (
                "No has seleccionado ningún canal de destino.\n\n"
                "Elige un webhook en el selector antes de subir.")

        # 7. ¿La URL del webhook elegido sigue siendo válida?
        if not url:
            return None, None, (
                f"El webhook «{name}» no tiene URL configurada.\n\n"
                "Ve a Configuración y completa su URL.")

        # 8. ¿Existe credentials.json?
        if not os.path.exists(CREDS_JSON):
            return None, None, (
                "Falta el archivo credentials.json en la carpeta config/.\n\n"
                "Descárgalo desde Google Cloud Console.")

        return url, name, None

    # ── SUBIDA ────────────────────────────────────────────
    def _start_upload(self):
        webhook_url, webhook_name, err = self._validate_pre_upload()
        if err:
            self.add_log(f"Abortado: {err.splitlines()[0]}", "error")
            styled_error(self, "No se puede subir", err)
            return

        filepath = self._selected_file

        # Obtener info del video
        try:
            cap          = cv2.VideoCapture(filepath)
            fps          = cap.get(cv2.CAP_PROP_FPS) or 30
            frames       = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            secs         = int(frames / fps) if fps > 0 else 0
            duration_str = f"{secs // 60}:{secs % 60:02d}"
        except Exception as e:
            styled_error(self, "Error al leer el video",
                         f"No se pudo leer la información del video:\n{e}")
            return

        size_str = format_size(filepath)

        confirm = styled_ask(
            self, "Confirmar subida",
            f"¿Subir este video y enviarlo a Discord?\n\n"
            f"Archivo:   {os.path.basename(filepath)}\n"
            f"Duración:  {duration_str}\n"
            f"Tamaño:    {size_str}\n"
            f"Canal:     {webhook_name}")
        if not confirm:
            return

        self._cancel_event.clear()
        self.uploading = True
        self._set_upload_mode(True)

        threading.Thread(
            target=self._process_upload,
            args=(filepath, duration_str, webhook_url),
            daemon=True).start()

    def cancel_upload(self):
        if self.uploading:
            self._cancel_event.set()
            self.after(0, self.add_log, "Cancelando subida...", "warn")

    def _set_upload_mode(self, active: bool):
        if active:
            self.upload_btn.config(state="disabled", bg="#3A6B3A")
            self.cancel_btn.config(state="normal")
            self._progress_frame.pack(fill="x", pady=(10, 0))
            self._progress_bar.pack(fill="x")
            self._progress_bar.start(12)
        else:
            self.upload_btn.config(state="normal", bg=FG_OK)
            self.cancel_btn.config(state="disabled")
            self._progress_bar.stop()
            self._progress_frame.pack_forget()

    def _process_upload(self, filepath, duration_str, webhook_url):
        filename = os.path.basename(filepath)
        try:
            self.after(0, self.add_log, f"Iniciando subida: {filename}", "info")
            self.after(0, self.set_status, "upload")

            self.after(0, self.update_last_log, "Extrayendo thumbnail...", "info")
            thumb_path = extract_thumbnail(filepath)

            self.after(0, self.update_last_log, "Subiendo a Google Drive...", "info")
            file_id    = upload_to_drive(filepath, self._cancel_event)
            drive_link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

            thumb_url = None
            if thumb_path and os.path.exists(thumb_path):
                self.after(0, self.update_last_log, "Subiendo thumbnail...", "info")
                try:
                    thumb_url = upload_thumbnail_to_drive(thumb_path)
                except Exception as e:
                    self.after(0, self.add_log,
                               f"Thumbnail omitido (error no crítico): {e}", "warn")
                finally:
                    try:
                        os.remove(thumb_path)
                    except:
                        pass

            self.after(0, self.update_last_log, "Enviando a Discord...", "info")
            send_to_discord(drive_link, filepath, duration_str, thumb_url, webhook_url)

            self.after(0, self.add_log, f"✓  Completado: {filename}", "ok")
            self.after(0, self.set_status, "ok")

            # Limpiar selección de archivo tras subida exitosa
            self.after(0, self._clear_file_selection)

        except InterruptedError:
            self.after(0, self.add_log, "Subida cancelada por el usuario.", "warn")
            self.after(0, self.set_status, "cancel")

        except FileNotFoundError as e:
            msg = str(e)
            self.after(0, self.add_log, f"Archivo no encontrado: {msg}", "error")
            self.after(0, self.set_status, "error")
            self.after(0, lambda: styled_error(
                self, "Archivo no encontrado", msg))

        except ConnectionError as e:
            msg = str(e)
            self.after(0, self.add_log, f"Error de conexión: {msg}", "error")
            self.after(0, self.set_status, "error")
            self.after(0, lambda: styled_error(
                self, "Error de conexión", msg))

        except PermissionError as e:
            msg = str(e)
            self.after(0, self.add_log, f"Permiso denegado: {msg}", "error")
            self.after(0, self.set_status, "error")
            self.after(0, lambda: styled_error(
                self, "Permiso denegado",
                f"No se tiene permiso para leer el archivo.\n\n{msg}"))

        except Exception as e:
            msg = str(e)
            self.after(0, self.add_log, f"Error inesperado: {msg}", "error")
            self.after(0, self.set_status, "error")
            self.after(0, lambda: styled_error(
                self, "Error inesperado", msg))

        finally:
            self.uploading = False
            self._cancel_event.clear()
            self.after(0, self._set_upload_mode, False)

    def _clear_file_selection(self):
        self._selected_file = None
        self._file_label.config(text="Ningún archivo seleccionado", fg=FG_MUTED)

    def open_settings(self):
        win = SettingsWindow(self)
        # Al cerrar configuración, refrescar selector de webhooks
        self.wait_window(win)
        self._webhook_selector.refresh()

        # Recargar .env para que los cambios sean visibles
        load_dotenv(ENV_PATH, override=True)
        self._webhook_selector.refresh()


# ══════════════════════════════════════════════════════════
# WEBHOOK CARD — formulario de nombre + URL
# ══════════════════════════════════════════════════════════
class WebhookCard(tk.Frame):
    def __init__(self, parent, index, **kw):
        super().__init__(parent, bg=BG_CARD, padx=14, pady=12,
                         highlightthickness=1, highlightbackground=DIVIDER, **kw)
        self.index = index
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=BG_CARD)
        hdr.pack(fill="x", pady=(0, 10))

        self._dot    = tk.Canvas(hdr, width=8, height=8,
                                 bg=BG_CARD, highlightthickness=0)
        self._dot.pack(side="left", padx=(0, 6))
        self._dot_id = self._dot.create_oval(1, 1, 7, 7, fill=FG_MUTED, outline="")

        tk.Label(hdr, text=f"WEBHOOK #{self.index + 1}",
                 bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL).pack(side="left")

        tk.Label(self, text="NOMBRE", bg=BG_CARD,
                 fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        self.name_var = tk.StringVar(
            value=os.getenv(f"DISCORD_WEBHOOK_NAME_{self.index}", ""))
        self.name_entry = tk.Entry(self, textvariable=self.name_var,
                                   font=FONT_UI, bg=BG_INPUT, fg=FG_WHITE,
                                   relief="flat", insertbackground=FG_WHITE,
                                   selectbackground=ACCENT)
        self.name_entry.pack(fill="x", ipady=5, pady=(3, 10))

        tk.Label(self, text="URL DEL WEBHOOK", bg=BG_CARD,
                 fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        self.url_var = tk.StringVar(
            value=os.getenv(f"DISCORD_WEBHOOK_{self.index}", ""))
        self.url_entry = tk.Entry(self, textvariable=self.url_var,
                                  font=FONT_MONO, bg=BG_INPUT, fg=FG_WHITE,
                                  relief="flat", insertbackground=FG_WHITE,
                                  selectbackground=ACCENT)
        self.url_entry.pack(fill="x", ipady=5)

        # Indicador visual de si tiene datos
        self.name_var.trace_add("write", lambda *_: self._refresh_dot())
        self.url_var.trace_add("write",  lambda *_: self._refresh_dot())
        self._refresh_dot()

    def _refresh_dot(self):
        has_data = bool(self.name_var.get().strip() and self.url_var.get().strip())
        self._dot.itemconfig(self._dot_id, fill=FG_OK if has_data else FG_MUTED)


# ══════════════════════════════════════════════════════════
# VENTANA DE CONFIGURACION
# ══════════════════════════════════════════════════════════
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Configuración — Violet Uploader")
        self.geometry("500x720")
        self.configure(bg=BG_BASE)
        try:
            self.iconbitmap("icono.ico")
        except:
            pass
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        # Topbar
        topbar = tk.Frame(self, bg=BG_CARD, height=44)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text="Configuración",
                 bg=BG_CARD, fg=FG_WHITE, font=FONT_TITLE).pack(side="left", padx=14)
        tk.Frame(self, bg=DIVIDER, height=1).pack(fill="x")

        # Área scrollable
        wrap = tk.Frame(self, bg=BG_BASE)
        wrap.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(wrap, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        canvas = tk.Canvas(wrap, bg=BG_BASE, highlightthickness=0,
                           yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=canvas.yview)

        body = tk.Frame(canvas, bg=BG_BASE)
        win  = canvas.create_window((0, 0), window=body, anchor="nw")

        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        body.bind("<Configure>",   lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ── SECCIÓN: Google Drive ──────────────────────────
        self._build_drive_section(body)

        tk.Frame(body, bg=DIVIDER, height=1).pack(fill="x", padx=16, pady=(18, 0))

        # ── SECCIÓN: Webhooks ─────────────────────────────
        sec = tk.Frame(body, bg=BG_BASE)
        sec.pack(fill="x", padx=16, pady=(18, 0))
        tk.Label(sec, text="WEBHOOKS DE DISCORD",
                 bg=BG_BASE, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        tk.Label(sec,
                 text="Configura hasta 5 destinos. El canal se elige desde la pantalla principal.",
                 bg=BG_BASE, fg=FG_MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 12))

        self.cards = []
        for i in range(5):
            card = WebhookCard(body, i)
            card.pack(fill="x", padx=16, pady=(0, 10))
            self.cards.append(card)

        # Footer
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

    # ── SECCIÓN GOOGLE DRIVE ──────────────────────────────
    def _build_drive_section(self, body):
        sec = tk.Frame(body, bg=BG_BASE)
        sec.pack(fill="x", padx=16, pady=(18, 0))
        tk.Label(sec, text="GOOGLE DRIVE",
                 bg=BG_BASE, fg=FG_MUTED, font=FONT_SMALL).pack(anchor="w")
        tk.Label(sec, text="Cuenta donde se subirán los videos.",
                 bg=BG_BASE, fg=FG_MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 10))

        drive_card = tk.Frame(body, bg=BG_CARD, padx=14, pady=14,
                              highlightthickness=1, highlightbackground=DIVIDER)
        drive_card.pack(fill="x", padx=16, pady=(0, 8))

        # Estado de la cuenta
        status_row = tk.Frame(drive_card, bg=BG_CARD)
        status_row.pack(fill="x", pady=(0, 10))

        self._drive_dot = tk.Canvas(status_row, width=10, height=10,
                                    bg=BG_CARD, highlightthickness=0)
        self._drive_dot.pack(side="left", padx=(0, 8))
        self._drive_dot_id = self._drive_dot.create_oval(
            1, 1, 9, 9, fill=FG_MUTED, outline="")

        self._drive_status_lbl = tk.Label(
            status_row, text="Comprobando...", bg=BG_CARD,
            fg=FG_MUTED, font=FONT_BOLD)
        self._drive_status_lbl.pack(side="left")

        # Email de la cuenta
        self._drive_email_lbl = tk.Label(
            drive_card, text="", bg=BG_CARD, fg=FG_MUTED, font=FONT_SMALL)
        self._drive_email_lbl.pack(anchor="w", pady=(0, 12))

        # Botones
        drive_btn_row = tk.Frame(drive_card, bg=BG_CARD)
        drive_btn_row.pack(fill="x")

        if not os.path.exists(CREDS_JSON):
            # Sin credentials.json: mostrar aviso
            tk.Label(drive_card,
                     text="⚠  Falta credentials.json en config/.\n"
                          "Descárgalo desde Google Cloud Console.",
                     bg=BG_CARD, fg=FG_WARN, font=FONT_SMALL,
                     justify="left").pack(anchor="w", pady=(0, 10))

        self._login_btn = tk.Button(
            drive_btn_row, text="Iniciar sesión con Google",
            bg=ACCENT, fg=FG_WHITE, activebackground=ACCENT_LT,
            activeforeground=FG_WHITE, relief="flat", font=FONT_BOLD,
            padx=14, pady=5, cursor="hand2",
            command=self._do_google_login)
        self._login_btn.pack(side="left", padx=(0, 8))

        self._logout_btn = tk.Button(
            drive_btn_row, text="Cerrar sesión",
            bg=BG_INPUT, fg=FG_MUTED, activebackground=DIVIDER,
            activeforeground=FG_WHITE, relief="flat", font=FONT_UI,
            padx=14, pady=5, cursor="hand2",
            command=self._do_logout)
        self._logout_btn.pack(side="left")

        self._refresh_drive_status()

    def _refresh_drive_status(self):
        logged = is_logged_in()
        if logged:
            self._drive_dot.itemconfig(self._drive_dot_id, fill=FG_OK)
            self._drive_status_lbl.config(text="Sesión activa", fg=FG_OK)
            # Intentar obtener email en hilo para no bloquear UI
            def _fetch_email():
                email = get_google_account_email()
                if email:
                    self.after(0, self._drive_email_lbl.config,
                               {"text": email, "fg": FG_MUTED})
            threading.Thread(target=_fetch_email, daemon=True).start()
            self._login_btn.config(state="disabled", bg=BG_INPUT,
                                   fg=FG_MUTED, text="Ya estás autenticado")
            self._logout_btn.config(state="normal")
        else:
            self._drive_dot.itemconfig(self._drive_dot_id, fill=FG_ERR)
            self._drive_status_lbl.config(text="Sin sesión", fg=FG_ERR)
            self._drive_email_lbl.config(text="")
            self._login_btn.config(state="normal", bg=ACCENT, fg=FG_WHITE,
                                   text="Iniciar sesión con Google")
            self._logout_btn.config(state="disabled")

    def _do_google_login(self):
        if not os.path.exists(CREDS_JSON):
            styled_error(self, "credentials.json no encontrado",
                         "Coloca el archivo credentials.json en la carpeta config/ "
                         "antes de iniciar sesión.\n\n"
                         "Puedes descargarlo desde Google Cloud Console.")
            return

        self._login_btn.config(state="disabled", text="Abriendo navegador...")
        self.update()

        def _login_thread():
            try:
                get_drive_service()   # dispara el flujo OAuth
                self.after(0, self._on_login_success)
            except Exception as e:
                self.after(0, self._on_login_error, str(e))

        threading.Thread(target=_login_thread, daemon=True).start()

    def _on_login_success(self):
        self._refresh_drive_status()
        self._flash("✓  Sesión iniciada correctamente.")

    def _on_login_error(self, msg):
        self._refresh_drive_status()
        styled_error(self, "Error al iniciar sesión",
                     f"No se pudo completar la autenticación con Google.\n\n{msg}")

    def _do_logout(self):
        confirm = styled_ask(
            self, "Cerrar sesión",
            "¿Cerrar sesión de Google Drive?\n\n"
            "Tendrás que volver a autenticarte para subir videos.")
        if not confirm:
            return
        try:
            if os.path.exists(TOKEN_PICKLE):
                os.remove(TOKEN_PICKLE)
            self._refresh_drive_status()
            self._flash("✓  Sesión cerrada.")
        except Exception as e:
            styled_error(self, "Error", f"No se pudo cerrar la sesión:\n{e}")

    # ── GUARDAR WEBHOOKS ──────────────────────────────────
    def _save(self):
        # Validar: al menos un webhook con nombre y URL
        any_valid = False
        for card in self.cards:
            name = card.name_var.get().strip()
            url  = card.url_var.get().strip()
            if name and url:
                any_valid = True
            elif name and not url:
                styled_warn(self, "Webhook incompleto",
                            f"El webhook «{name}» tiene nombre pero no tiene URL.\n\n"
                            "Completa la URL o deja ambos campos vacíos.")
                return
            elif not name and url:
                styled_warn(self, "Webhook incompleto",
                            f"Hay un webhook con URL pero sin nombre (#{card.index+1}).\n\n"
                            "Añade un nombre o deja ambos campos vacíos.")
                return

        for card in self.cards:
            i = card.index
            set_key(ENV_PATH, f"DISCORD_WEBHOOK_{i}",      card.url_var.get().strip())
            set_key(ENV_PATH, f"DISCORD_WEBHOOK_NAME_{i}", card.name_var.get().strip())

        load_dotenv(ENV_PATH, override=True)
        self._flash("✓  Cambios guardados.")

    def _flash(self, msg):
        lbl = tk.Label(self, text=msg, bg=BG_CARD,
                       fg=FG_OK, font=FONT_SMALL, anchor="w", padx=14)
        lbl.pack(fill="x", side="bottom", pady=(0, 4))
        self.after(3500, lbl.destroy)


if __name__ == "__main__":
    app = App()
    app.mainloop()