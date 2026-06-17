# Violet Uploader

Aplicación web para Windows que permite subir archivos y carpetas a Google Drive preservando la estructura de directorios, con notificaciones a Discord y miniaturas automáticas.

## Características

- **Subida de cualquier tipo de archivo** — videos, imágenes, documentos, audio, etc.
- **Subida de carpetas completas** — preserva la estructura de subdirectorios en Google Drive
- **Arrastrar y soltar** — carpetas y archivos desde el explorador de Windows
- **Google Drive API** — autenticación OAuth, archivos públicos visibles desde cualquier enlace
- **Notificaciones a Discord** — embed con miniatura, duración (video), tamaño, tipo de archivo y fecha
- **Múltiples webhooks** — hasta 5 canales de Discord configurables desde la interfaz
- **Thumbnails automáticos** — extraídos del primer video o imagen encontrados
- **Interfaz oscura** — estilo Discord
- **Ventana nativa** — usando pywebview (fallback a navegador si no está disponible)

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

### 3. Configurar Google Drive API

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto
3. Habilita la **Google Drive API**
4. Ve a **Credenciales** → **Crear credenciales** → **ID de cliente OAuth**
5. Selecciona tipo **Aplicación de escritorio**
6. Descarga el archivo `credentials.json`
7. Crea la carpeta `config/` y coloca `credentials.json` allí

### 4. Configurar webhooks de Discord (opcional)

Copia `.env.example` a `.env` y configura los webhooks, o hazlo desde la interfaz de la app.

### 5. Ejecutar

```
python app.py
```

La primera vez que inicies sesión se abrirá el navegador para autorizar el acceso a Google Drive. El token se guarda automáticamente en `config/token.pickle`.

## Compilar a .exe (opcional)

```
pip install pyinstaller
build.bat
```

El ejecutable se crea en `dist/Violet.exe`. Coloca la carpeta `config/` con `credentials.json` junto al `.exe`.

## Licencia

MIT
