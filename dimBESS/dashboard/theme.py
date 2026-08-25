"""Paleta corporativa Netonpower, extraída del logo (dashboard/logo.png)."""

from pathlib import Path

from PIL import Image

LOGO_PATH = str(Path(__file__).resolve().parent / "logo.png")
LOGO_FULL_PATH = str(Path(__file__).resolve().parent / "logo_completo.png")
LOGO_FULL_WHITE_PATH = str(Path(__file__).resolve().parent / "logo_completo_blanco.png")

def logo_image():
    """
    Objeto PIL.Image fresco para page_icon=... (en vez de la ruta como string: en
    Streamlit 1.52 pasar la ruta directamente rompe la barra lateral de navegación
    multipágina). Debe ser una instancia NUEVA en cada llamada, no un singleton
    reutilizado: Pillow libera el estado interno del PNG tras el primer .load()/.save(),
    así que reutilizar el mismo objeto Image en páginas/reruns sucesivos revienta con
    "AssertionError: self.png is not None" a partir del segundo uso.
    """
    return Image.open(LOGO_PATH)

CORAL_DARK = "#C24A4C"
CORAL_LIGHT = "#D06365"
NAVY_DARK = "#2E2C67"   # solo UI: botones/texto (primaryColor). Demasiado oscuro para marca de dato.
ORANGE = "#DFA06A"
CYAN = "#35BDD7"

# Variantes "chart-safe": mismo matiz que la marca pero con L/C ajustados para
# pasar las bandas del validador de dataviz (OKLCH L 0.43-0.77, C >= 0.10) cuando
# se usan como marca de dato (barra/línea/quesito), no como color de UI.
CHART_NAVY = "#4B499B"
CHART_NAVY_LIGHT = "#6A78CD"
CHART_CYAN_SOFT = "#00B4CA"

MUTED = "#B5B5B5"  # categoría secundaria/poco importante (ej. excedente no almacenado)

# Rampa secuencial (coral, claro->oscuro) para heatmaps/magnitud
HEATMAP_LIGHT = "#FCE1DF"
HEATMAP_DARK = "#AC3036"

# Tintas pastel (marca + ~85% blanco) para fondos de header/metric-cell de resultados
CORAL_TINT = "#F6E4E4"
NAVY_TINT = "#E3E2ED"
ORANGE_TINT = "#FAF1E9"
CYAN_TINT = "#E1F5F9"
