import random


def tirar_dado(parameters: dict) -> str:
    """
    Simula el tiro de un dado de seis caras y retorna el resultado.

    Args:
        parameters (dict): Un diccionario de parámetros (no usado en esta función,
                           pero requerido por la firma).

    Returns:
        str: Un string que indica el número en el que cayó el dado.
    """
    resultado = random.randint(1, 6)
    return f"El dado cayó en: {resultado}"


TOOL_DEF = {
    "name": "tirar_dado",
    "description": "Lanza un dado virtual de 6 caras y devuelve el resultado. Úsalo cuando el usuario pida tirar un dado o probar su suerte.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "lanzar"}
        },
        "required": ["action"]
    }
}