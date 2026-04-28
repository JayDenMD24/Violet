# Violet Uploader v1.2

Aplicación de escritorio para Windows que permite subir videos a Google Drive y enviar notificaciones a Discord con miniatura, duración, tamaño y fecha del archivo.

## Características

- Subida manual de videos a Google Drive
- Notificación a Discord con nombre, duración, tamaño, fecha, hora y miniatura del archivo
- Interfaz oscura con estética Discord
- Configuración de múltiples webhooks de Discord (hasta 5)
- Gestión de autenticación desde la app

## Requisitos

- Windows 10 o superior
- Python 3.10+
- Cuenta de Google con acceso a Google Drive API
- Webhook(s) de Discord

## Instalación

### 1. Clonar el repositorio

```
git clone https://github.com/tu-usuario/Violet.git
cd Violet
```

### 2. Crear entorno virtual e instalar dependencias

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Copia `.env.example` a `.env`:

```
copy .env.example .env
```

Configura los webhooks de Discord (opcional, también puedes hacerlo desde la app):

```
DISCORD_WEBHOOK_0=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_NAME_0=Mi Canal
```

### 4. Configurar Google Drive API

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto
3. Habilita la **Google Drive API**
4. Ve a **Credenciales** → **Crear credenciales** → **OAuth 2.0 (ID de cliente OAuth)**
5. Selecciona tipo **Aplicación de escritorio**
6. Descarga el archivo `credentials.json`
7. Coloca `credentials.json` en la carpeta `config/`

La primera vez que inicies sesión desde la app, se abrirá el navegador para autorizar el acceso. El token se guardará automáticamente en `config/token.pickle`.

### 5. Ejecutar

```
python violet_uploader.py
```

## Configuración desde la app

Desde el botón **Configuración** en la interfaz puedes:

- Iniciar/cerrar sesión con Google Drive
- Añadir hasta 5 webhooks de Discord (nombre + URL)
- Los cambios se guardan automáticamente en `.env`

## Compilar a .exe

```
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icono.ico --name "Violet Uploader" violet_uploader.py
```

El ejecutable quedará en la carpeta `dist/`. Asegúrate de tener `icono.ico`, `.env` y la carpeta `config/` con `credentials.json` en la misma carpeta que el `.exe`.

## LICENCIA

MIT