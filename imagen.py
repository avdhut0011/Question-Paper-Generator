# -*- coding: utf-8 -*-
# Modern Google Generative AI imports for Gemini 2.5 Flash Image
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
    NEW_API = True
    print("[OK] Google Generative AI (new API) loaded successfully")
except ImportError:
    try:
        import google.generativeai as genai
        GENAI_AVAILABLE = True
        NEW_API = False
        print("[OK] Google Generative AI (legacy) loaded successfully")
    except ImportError:
        GENAI_AVAILABLE = False
        NEW_API = False
        print("[WARNING] Google Generative AI not available for image generation")

from PIL import Image
from io import BytesIO
import base64
import os
import logging
import requests
import json

# Configure logging
logger = logging.getLogger("ImageGenerator")

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Use Gemini PRO API key for the paid 2.5 Flash Image model
API_KEY = os.environ.get("GEMINI_API_KEY_PRO")

# Modern API configuration for Gemini 2.5 Flash Image
if GENAI_AVAILABLE and NEW_API:
    try:
        client = genai.Client(api_key=API_KEY)
        print("[OK] Google Generative AI configured for Gemini 2.5 Flash Image generation (PRO API)")
    except Exception as e:
        print(f"[WARNING] Failed to configure Google Generative AI: {e}")
        GENAI_AVAILABLE = False
        client = None
else:
    client = None

def generate_diagram_image(prompt, output_filename='diagram_image.png'):
    """
    Generate a diagrammatic image using Gemini 2.5 Flash Image model.
    Returns the output filename if successful, else None.
    """
    if not API_KEY:
        logger.error("GEMINI_API_KEY_PRO not found in environment variables")
        return None
        
    if not GENAI_AVAILABLE:
        logger.error("Google Generative AI not available")
        return None
        
    try:
        model_name = "gemini-2.5-flash-image"
        logger.info(f"[IMAGE] Starting image generation using {model_name}")
        logger.info(f"[PROMPT] Prompt: {prompt[:100]}...")
        
        # Enhanced prompt for better diagram generation following best practices
        enhanced_prompt = f"""Create a clear, educational diagram for the following:

{prompt}

Requirements:
- Make it visually clear and educational
- Use appropriate labels and annotations where necessary
- Ensure it's suitable for academic use
- Use clean, simple design with good contrast
- Focus on clarity and educational value
- Include essential diagram indicators (A, B, 1, 2, etc.) where helpful
- Make it professional and print-friendly

Style: Clean educational diagram, well-labeled, high contrast, suitable for textbooks."""
        
        # Try new API first, then fallback to REST API
        if NEW_API and client:
            logger.info("[API] Using new Gemini client API...")
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[enhanced_prompt],
                )
                
                # Process the response parts
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            # Handle text responses
                            if part.text is not None:
                                logger.info(f"[TEXT] Model response: {part.text[:100]}...")
                            
                            # Handle image data
                            elif part.inline_data is not None:
                                logger.info("[IMAGE] Image data found in response")
                                image = Image.open(BytesIO(part.inline_data.data))
                                image.save(output_filename)
                                logger.info(f"[OK] Image saved successfully as {output_filename}")
                                return output_filename
                
            except Exception as new_api_error:
                logger.warning(f"[WARN] New API failed: {new_api_error}")
                logger.info("[FALLBACK] Trying REST API...")
        
        # Fallback to REST API
        logger.info("[API] Using REST API for image generation...")
        
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        url = f"{base_url}/models/{model_name}:generateContent"
        
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY
        }
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": enhanced_prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 2048
            }
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        if response.status_code == 429:
            logger.warning("[QUOTA] API quota exceeded. Please check your billing or wait for quota reset.")
            # Try to extract retry time from response
            try:
                error_data = response.json()
                if "error" in error_data and "details" in error_data["error"]:
                    for detail in error_data["error"]["details"]:
                        if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                            retry_delay = detail.get("retryDelay", "unknown")
                            logger.info(f"[RETRY] Suggested retry delay: {retry_delay}")
            except:
                pass
            return None
        elif response.status_code != 200:
            logger.error(f"[ERROR] API request failed with status {response.status_code}")
            logger.error(f"[ERROR] Response: {response.text}")
            return None
        
        response_data = response.json()
        logger.info("[RESPONSE] Processing REST API response...")
        
        # Extract image data from response
        if "candidates" in response_data and response_data["candidates"]:
            candidate = response_data["candidates"][0]
            
            if "content" in candidate and "parts" in candidate["content"]:
                for part in candidate["content"]["parts"]:
                    # Check for inline data (image)
                    if "inlineData" in part:
                        logger.info("[IMAGE] Image data found in response")
                        image_data = part["inlineData"]["data"]
                        
                        # Decode and save image
                        if isinstance(image_data, str):
                            image_bytes = base64.b64decode(image_data)
                        else:
                            image_bytes = image_data
                            
                        image = Image.open(BytesIO(image_bytes))
                        image.save(output_filename)
                        logger.info(f"[OK] Image saved successfully as {output_filename}")
                        return output_filename
                    
                    # Log text responses for debugging
                    elif "text" in part:
                        logger.info(f"[TEXT] Text response: {part['text'][:100]}...")
        
        logger.warning("[WARN] No image data found in response")
        
    except requests.exceptions.Timeout:
        logger.error("[ERROR] Request timed out")
    except requests.exceptions.RequestException as e:
        logger.error(f"[ERROR] Request failed: {e}")
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error during image generation: {e}")
        import traceback
        logger.error(f"[TRACE] Full traceback: {traceback.format_exc()}")
    
    return None


def test_image_generation():
    """
    Test function to validate image generation functionality.
    """
    print("\n" + "="*50)
    print("TESTING GEMINI 2.5 FLASH IMAGE GENERATION")
    print("="*50)
    
    # Configuration check
    print(f"API Key Available: {'✅' if API_KEY else '❌'}")
    print(f"GenAI Available: {'✅' if GENAI_AVAILABLE else '❌'}")
    print(f"New API: {'✅' if NEW_API else '❌'}")
    print(f"Client Available: {'✅' if client else '❌'}")
    
    if not API_KEY:
        print("\n❌ GEMINI_API_KEY_PRO not found in environment variables")
        print("Please check your .env file")
        return
    
    # Test prompts
    test_prompts = [
        "A simple diagram showing the parts of a plant cell with labels",
        "Create a diagram of the water cycle with arrows showing the process",
        "Draw a basic food chain diagram with 4 organisms"
    ]
    
    for i, prompt in enumerate(test_prompts, 1):
        print(f"\nTest {i}: {prompt}")
        print("-" * 40)
        
        output_file = f"test_image_{i}.png"
        result = generate_diagram_image(prompt, output_file)
        
        if result:
            print(f"✅ SUCCESS: Image generated and saved as {result}")
        else:
            print("❌ FAILED: Could not generate image")
    
    print("\n" + "="*50)
    print("IMAGE GENERATION TESTING COMPLETE")
    print("="*50)


def generate_single_test_image(prompt="A simple diagram of a water molecule showing hydrogen and oxygen atoms"):
    """
    Generate a single test image with a simple prompt.
    """
    print(f"\n🎨 Generating test image...")
    print(f"Prompt: {prompt}")
    
    result = generate_diagram_image(prompt, "single_test_image.png")
    
    if result:
        print(f"✅ SUCCESS: Image saved as {result}")
        if os.path.exists(result):
            print(f"📁 File size: {os.path.getsize(result)} bytes")
    else:
        print("❌ FAILED: Could not generate image")
    
    return result


def test_image_models():
    """
    Test different image model names to find working ones.
    """
    print("\n🔍 Testing different image models...")
    
    if not API_KEY:
        print("❌ No API key available")
        return
    
    # Different possible model names
    models_to_test = [
        "gemini-2.5-flash-image",
        "gemini-2.5-flash-image-preview", 
        "gemini-2.0-flash-image",
        "gemini-pro-vision"
    ]
    
    base_url = "https://generativelanguage.googleapis.com/v1beta"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": API_KEY
    }
    
    simple_prompt = "A simple red dot"
    
    for model in models_to_test:
        print(f"\nTesting {model}...")
        
        url = f"{base_url}/models/{model}:generateContent"
        payload = {
            "contents": [{
                "parts": [{
                    "text": simple_prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 100
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                print(f"✅ {model} - SUCCESS")
                return model
            elif response.status_code == 404:
                print(f"❌ {model} - Model not found")
            elif response.status_code == 429:
                print(f"⚠️ {model} - Quota exceeded")
            else:
                print(f"❌ {model} - Error {response.status_code}")
                
        except Exception as e:
            print(f"❌ {model} - Connection error: {e}")
    
    print("\n❌ No working image models found")
    return None


def test_api_connection():
    """
    Test API connection without generating images.
    """
    print("\n🔍 Testing API connection...")
    
    if not API_KEY:
        print("❌ No API key available")
        return False
    
    try:
        # Test with a simple text-only request to check API access
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        url = f"{base_url}/models/gemini-2.5-flash:generateContent"
        
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY
        }
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": "Hello"
                }]
            }],
            "generationConfig": {
                "maxOutputTokens": 10
            }
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            print("✅ API connection successful")
            return True
        elif response.status_code == 429:
            print("⚠️ API quota exceeded")
            return False
        else:
            print(f"❌ API error: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def validate_setup():
    """
    Validate the setup without making API calls.
    """
    print("\n" + "="*50)
    print("GEMINI 2.5 FLASH IMAGE SETUP VALIDATION")
    print("="*50)
    
    # Show which API key is being used
    api_key_display = API_KEY[:10] + "..." + API_KEY[-4:] if API_KEY else "None"
    print(f"Using API Key: {api_key_display}")
    
    checks = [
        ("API Key (PRO)", API_KEY is not None),
        ("Google GenAI Library", GENAI_AVAILABLE),
        ("PIL Library", True),  # Already imported successfully
        ("Requests Library", True),  # Already imported successfully
        ("Environment File", os.path.exists('.env')),
    ]
    
    all_good = True
    for check_name, status in checks:
        status_icon = "✅" if status else "❌"
        print(f"{status_icon} {check_name}")
        if not status:
            all_good = False
    
    print(f"\nModel: gemini-2.5-flash-image")
    print(f"API Endpoint: https://generativelanguage.googleapis.com/v1beta")
    
    # Test API connection
    if API_KEY:
        api_works = test_api_connection()
        if api_works:
            print(f"\n✅ Setup is ready for Gemini 2.5 Flash Image generation!")
        else:
            print(f"\n⚠️ Setup ready but API has quota/access issues")
    else:
        print(f"\n❌ Setup issues detected. Please resolve before testing.")
    
    print("="*50)


if __name__ == "__main__":
    # Run setup validation first
    validate_setup()
    
    # Run tests when script is executed directly
    test_image_generation()