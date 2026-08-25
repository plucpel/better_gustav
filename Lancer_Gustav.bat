@echo off
chcp 65001 >nul
title GUSTAV - Calculateur de Tubes Sanguins (CHU de Québec)

echo =====================================================================
echo   🏥 GUSTAV - Calculateur de Tubes de Prélèvement (CHU de Québec)
echo =====================================================================
echo.

:: Vérification de Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas détecté sur ce poste Windows.
    echo Veuillez installer Python (avec l'option 'Add Python to PATH') depuis python.org
    echo ou utiliser la version portable 'Gustav_Windows_Portable.zip'.
    echo.
    pause
    exit /b 1
)

:: Installation des dépendances si nécessaire
echo [*] Vérification des dépendances...
pip install -q -r requirements.txt

:: Lancement du navigateur après 1.5s
start "" timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000

:: Démarrage de l'application
echo [*] Démarrage du serveur local sur http://127.0.0.1:8000 ...
echo [INFO] Pour arrêter l'application, fermez simplement cette fenêtre.
echo.
python app.py

pause
