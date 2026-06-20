@echo off
pyinstaller --onefile --windowed --name "Violet" ^
  --icon=static\img\icon.ico ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --hidden-import googleapiclient ^
  --hidden-import google_auth_oauthlib ^
  --hidden-import cv2 ^
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import certifi ^
  --collect-all certifi ^
  app.py
