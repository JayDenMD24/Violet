# Violet Recorder

Aplicación de escritorio para Windows que detecta automáticamente cuando OBS termina una grabación, sube el archivo a Google Drive y envía una notificación a Discord con los detalles.

## Características

- Conexión con OBS via WebSocket
- Subida automática a Google Drive al finalizar la grabación
- Notificación a Discord con nombre, duración, tamaño, fecha y hora del archivo
- Interfaz oscura con estética Discord

## Requisitos

- Windows 10 o superior
- Python 3.10+
- OBS Studio con el plugin WebSocket habilitado (incluido desde OBS 28+)
- Cuenta de Google con acceso a Google Drive API
- Webhook de Discord

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

Copia `.env.example` a `.env` y rellena los valores:

```
cp .env.example .env
```

```
OBS_HOST=localhost
OBS_PORT=4455
OBS_PASSWORD=tu_contraseña_obs
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
```

### 4. Configurar Google Drive API

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto y habilita la **Google Drive API**
3. Crea credenciales de tipo **OAuth 2.0 (aplicación de escritorio)**
4. Descarga el archivo `credentials.json` y colócalo en la carpeta `config/`

La primera vez que ejecutes la app, se abrirá el navegador para autorizar el acceso. El token se guardará automáticamente en `config/token.pickle`.

### 5. Ejecutar

```
python violet_recorder.py
```

## Compilar a .exe

```
pip install pyinstaller
pyinstaller --onefile --windowed --icon="icono.ico" --name "Violet Recorder" violet_recorder.py
```

El ejecutable quedará en la carpeta `dist/`. Asegúrate de tener `icono.ico`, `.env` y la carpeta `config/` con `credentials.json` en la misma carpeta que el `.exe`.

## Configuración desde la app

Puedes cambiar los parámetros de OBS y el webhook de Discord desde el botón **Configuración** dentro de la app. Los cambios se guardan en `.env` y se aplican al reiniciar.

## Licencia

MIT
