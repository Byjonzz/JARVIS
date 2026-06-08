import os
import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# Cargamos tus credenciales del archivo .env
load_dotenv()
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = "http://127.0.0.1:8888/callback"

def spotify_control(parameters: dict) -> str:
    query = parameters.get("query", "").strip()
    
    if not query:
        return "Error: No especificaste qué canción o artista buscar."
        
    if not CLIENT_ID or not CLIENT_SECRET:
        return "Error: Faltan las credenciales SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en el archivo .env."
        
    try:
        # 🟢 1. EL DESPERTADOR: Forzamos a que Windows abra Spotify primero
        os.startfile("spotify:")
        
        # Le damos 3 segundos para que cargue y le avise a los servidores que ya está en línea
        time.sleep(4)

        # 2. AUTENTICACIÓN
        scope = "user-modify-playback-state user-read-playback-state"
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=scope,
            open_browser=False # Apagado porque ya te autorizaste antes
        ))
        
        # 3. BÚSQUEDA EXACTA EN LA BASE DE DATOS DE SPOTIFY
        results = sp.search(q=query, limit=1, type='track')
        if not results['tracks']['items']:
            return f"No se encontraron resultados en los servidores para '{query}'."
            
        track = results['tracks']['items'][0]
        track_uri = track['uri']
        track_name = track['name']
        artist_name = track['artists'][0]['name']
        
        # 4. BÚSQUEDA DEL DISPOSITIVO DESPIERTO
        devices = sp.devices()
        active_device = None
        
        if devices['devices']:
            for d in devices['devices']:
                if d['is_active']:
                    active_device = d['id']
                    break
            # Si lo abrió pero no lo marcó como activo, tomamos el primero de la lista
            if not active_device:
                active_device = devices['devices'][0]['id']
        else:
            # Si el internet está lento, le damos 2 segundos extra de gracia
            time.sleep(2)
            devices = sp.devices()
            if devices['devices']:
                active_device = devices['devices'][0]['id']
            else:
                return f"Spotify se abrió, pero tardó demasiado en conectarse a la red. Vuelve a pedir la canción."

        # 5. INYECCIÓN DIRECTA DE REPRODUCCIÓN
        sp.start_playback(device_id=active_device, uris=[track_uri])
        return f"Reproduciendo '{track_name}' de {artist_name} vía API Oficial."
        
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 404:
            return "Error 404: La computadora sigue marcada como inactiva. Asegúrate de reproducir una canción manualmente al menos una vez para registrarla."
        elif e.http_status == 403:
            return "Error 403: Spotify requiere que la cuenta sea Premium para inyectar órdenes de reproducción mediante su API."
        return f"Error en la API de Spotify: {e}"
    except Exception as e:
        return f"Error crítico controlando Spotify: {e}"

# 🟢 EL MANUAL PARA JARVIS
TOOL_DEF = {
    "name": "spotify_control",
    "description": "Abre la aplicación de Spotify y reproduce música usando la API Oficial REST. Úsalo cuando el usuario te pida poner música o una canción.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Nombre de la canción y/o artista a reproducir."}
        },
        "required": ["query"]
    }
}