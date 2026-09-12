@echo off
REM Usage: startServer.bat [port]

REM Check for cert and key and generate if they are missing
if not exist "server.crt" goto gencert
if not exist "server.key" goto gencert
goto runserver

:gencert
echo TLS cert or key missing, generating self-signed cert/key...
python generate_cert.py
if errorlevel 1 (
    echo Error: certificate generation failed. 1>&2
    exit /b 1
)

:runserver
python secure_server.py %*
