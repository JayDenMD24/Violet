import os
import sys
import tempfile

if getattr(sys, 'frozen', False):
    USER_DATA_DIR = os.path.dirname(sys.executable)
else:
    USER_DATA_DIR = os.path.dirname(os.path.abspath(__file__))

ENV_PATH = os.path.join(USER_DATA_DIR, ".env")
CONFIG_DIR = os.path.join(USER_DATA_DIR, "config")
CREDS_JSON = os.path.join(CONFIG_DIR, "credentials.json")
TOKEN_PICKLE = os.path.join(CONFIG_DIR, "token.pickle")
EMAIL_FILE = os.path.join(CONFIG_DIR, "email.txt")
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "violet_uploads")

if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)
