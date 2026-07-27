"""Paleta corporativa Netonpower, extraída del logo (dashboard/logo.png)."""

from pathlib import Path

from PIL import Image

LOGO_PATH = str(Path(__file__).resolve().parent / "logo.png")
LOGO_FULL_PATH = str(Path(__file__).resolve().parent / "logo_completo.png")

# Usar un objeto PIL.Image en vez de la ruta como string al pasarlo a
# st.set_page_config(page_icon=...): en Streamlit 1.52 pasar la ruta directamente
# rompe la barra lateral de navegación multipágina (bug interno de Streamlit).
LOGO_IMAGE = Image.open(LOGO_PATH)

CORAL_DARK = "#C24A4C"
CORAL_LIGHT = "#D06365"
NAVY_DARK = "#2E2C67"
NAVY_LIGHT = "#404980"
ORANGE = "#DFA06A"
ORANGE_LIGHT = "#EAC08F"
CYAN = "#35BDD7"
CYAN_SOFT = "#7FD5E3"

# Tintas pastel (marca + ~85% blanco) para fondos de metric-cell
CORAL_TINT = "#F6E4E4"
NAVY_TINT = "#E3E2ED"
ORANGE_TINT = "#FAF1E9"
CYAN_TINT = "#E1F5F9"
