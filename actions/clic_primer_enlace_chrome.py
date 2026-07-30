import pyautogui
import pygetwindow as gw
import time
import sys
import subprocess
import os

def clic_primer_enlace_chrome(parameters: dict) -> str:
    """
    Identifica el primer enlace visible en la ventana activa de Chrome y hace clic en él
    mediante automatización de interfaz de usuario (navegación por teclado).
    
    Args:
        parameters (dict): Parámetros opcionales. 
                           'wait_time' (float): Segundos a esperar entre acciones (default 0.5).
                           'tabs_to_link' (int): Veces a presionar Tab para llegar al primer enlace (default 1).
    
    Returns:
        str: Resultado de la operación.
    """
    wait_time = parameters.get('wait_time', 0.5)
    tabs_to_link = parameters.get('tabs_to_link', 1)
    
    # Configuración de seguridad de PyAutoGUI
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = wait_time

    try:
        # 1. Encontrar y activar la ventana de Chrome
        chrome_windows = gw.getWindowsWithTitle('Google Chrome')
        if not chrome_windows:
            # Intento alternativo para títulos localizados (ej. "Chrome", "Google Chrome - Perfil 1")
            all_windows = gw.getAllWindows()
            chrome_windows = [w for w in all_windows if 'chrome' in w.title.lower() and ('google' in w.title.lower() or 'new tab' in w.title.lower() or 'nueva pestaña' in w.title.lower() or len(w.title) < 20)]
            
        if not chrome_windows:
            return "Error: No se encontró ninguna ventana de Google Chrome abierta."

        chrome_win = chrome_windows[0]
        
        if chrome_win.isMinimized:
            chrome_win.restore()
            time.sleep(wait_time)
            
        chrome_win.activate()
        time.sleep(wait_time * 2) # Espera crítica para ganancia de foco

        # Verificar foco activo
        active_win = gw.getActiveWindow()
        if not active_win or 'chrome' not in active_win.title.lower():
             return "Error: No se pudo dar foco a la ventana de Chrome."

        # 2. Asegurar foco en el contenido de la página (no en la barra de direcciones)
        # Estrategia: Click en el centro de la ventana (área de viewport) -> Tab -> Enter
        # Coordenadas relativas a la ventana
        center_x = chrome_win.left + chrome_win.width // 2
        center_y = chrome_win.top + chrome_win.height // 2
        
        # Evitar barras de herramientas superiores (aprox 100px desde arriba)
        safe_y = chrome_win.top + 150 
        if safe_y > chrome_win.top + chrome_win.height - 50:
            safe_y = chrome_win.top + chrome_win.height // 2

        pyautogui.click(center_x, safe_y)
        time.sleep(wait_time)

        # 3. Navegación por teclado al primer elemento enfocable (enlace)
        # Presionar Tab N veces. Generalmente 1 o 2 veces desde el body llega al primer link.
        for _ in range(tabs_to_link):
            pyautogui.press('tab')
            time.sleep(wait_time / 2)

        # 4. Ejecutar clic (Enter) sobre el elemento enfocado
        pyautogui.press('enter')
        time.sleep(wait_time)

        return f"Éxito: Se ha navegado y pulsado Enter sobre el primer elemento enfocable en la ventana '{chrome_win.title}'."

    except gw.PyGetWindowException as e:
        return f"Error de gestión de ventanas: {str(e)}"
    except pyautogui.FailSafeException:
        return "Abortado: PyAutoGUI FailSafe activado (ratón en esquina)."
    except Exception as e:
        return f"Error inesperado durante la automatización: {type(e).__name__}: {str(e)}"

# Definición de la herramienta para Google Gemini Function Calling
TOOL_DEF = {
    "name": "clic_primer_enlace_chrome",
    "description": "Automatiza Chrome para hacer clic en el primer enlace visible utilizando navegación por teclado (Tab/Enter) y control de ventana nativo. Requiere pyautogui y pygetwindow.",
    "parameters": {
        "type": "object",
        "properties": {
            "wait_time": {
                "type": "number",
                "description": "Tiempo de espera en segundos entre acciones de UI (default: 0.5).",
                "default": 0.5
            },
            "tabs_to_link": {
                "type": "integer",
                "description": "Número de veces a presionar Tab para alcanzar el primer enlace desde el cuerpo de la página (default: 1).",
                "default": 1
            }
        },
        "required": []
    }
}