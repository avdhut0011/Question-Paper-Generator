import os
import logging
from dotenv import load_dotenv
import pytesseract

# Detect availability of Google Generative AI libraries
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except Exception:
    try:
        import google.generativeai as genai
        types = None
        GENAI_AVAILABLE = True
    except Exception:
        genai = None
        types = None
        GENAI_AVAILABLE = False

# Configure logging (kept identical to original logic)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("qp_generator.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("QPGenerator")

# Load environment and model selection
load_dotenv()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# API Key Configuration based on model version
API_KEY_2_0_FLASH = os.getenv("GEMINI_API_KEY")      # For 2.0-flash model
API_KEY_2_5_PRO = os.getenv("GEMINI_API_KEY_PRO")    # For 2.5 models (both flash and pro)

# Smart API key selection based on model
if "2.5" in GEMINI_MODEL:
    API_KEY = API_KEY_2_5_PRO
    print(f"Using PRO API key for {GEMINI_MODEL}")
elif "2.0" in GEMINI_MODEL:
    API_KEY = API_KEY_2_0_FLASH
    print(f"Using standard API key for {GEMINI_MODEL}")
else:
    API_KEY = API_KEY_2_0_FLASH
    print(f"Using fallback API key for {GEMINI_MODEL}")

if not API_KEY:
    raise ValueError(f"No API key found for model {GEMINI_MODEL}. Check your .env file.")

# Initialize Gemini client if available
if GENAI_AVAILABLE:
    if hasattr(genai, 'Client'):
        client = genai.Client(api_key=API_KEY)
    else:
        genai.configure(api_key=API_KEY)
        client = None
    print(f"[OK] Configured Gemini API for {GEMINI_MODEL}")
else:
    client = None

# Upload directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Set up Tesseract OCR path
pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD",
    r"D:\\Tesseract\\tesseract.exe"
)

# Exported names (module-level)
__all__ = [
    "client",
    "GENAI_AVAILABLE",
    "GEMINI_MODEL",
    "UPLOAD_DIR",
    "logger",
    "types",
    "genai",
]
