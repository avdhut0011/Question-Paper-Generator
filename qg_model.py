# qg_model.py
import os
from werkzeug.utils import secure_filename
import re
from services import legacy_provider as genai
from dotenv import load_dotenv
import fitz  # PyMuPDF
import pytesseract
from PIL import Image as PILImage
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.drawing.image import Image as XLImage
import time
import logging
import traceback
from typing import List, Tuple, Optional, Union
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.dimensions import ColumnDimension

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("qg_model.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("QuestionBankGenerator")

# Load environment variables and configure the generative AI model
load_dotenv()
import os
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# API Key Configuration based on model version
API_KEY_2_0_FLASH = os.getenv("GEMINI_API_KEY")      # For 2.0-flash model
API_KEY_2_5_PRO = os.getenv("GEMINI_API_KEY_PRO")    # For 2.5 models (both flash and pro)

# Smart API key selection based on model
if "2.5" in GEMINI_MODEL:
    # Both 2.5-flash and 2.5-pro use the same PRO API key
    API_KEY = API_KEY_2_5_PRO
    print(f"Using PRO API key for {GEMINI_MODEL}")
elif "2.0" in GEMINI_MODEL:
    # 2.0-flash uses the standard API key
    API_KEY = API_KEY_2_0_FLASH
    print(f"Using standard API key for {GEMINI_MODEL}")
else:
    # Fallback to standard API key
    API_KEY = API_KEY_2_0_FLASH
    print(f"Using fallback API key for {GEMINI_MODEL}")

if not API_KEY:
    raise ValueError(f"No API key found for model {GEMINI_MODEL}. Check your .env file.")

genai.configure(api_key=API_KEY)
print(f"[OK] Configured Gemini API for {GEMINI_MODEL}")

# Usage: set GEMINI_MODEL in .env to 'gemini-2.0-flash', 'gemini-2.5-pro', or 'gemini-2.5-flash'.
# API Keys:
# - GEMINI_API_KEY: For 2.0-flash model
# - GEMINI_API_KEY_PRO: For 2.5 models (both flash and pro)
#
# Example .env:
# GEMINI_MODEL=gemini-2.5-flash
# GEMINI_API_KEY=your-2.0-flash-key
# GEMINI_API_KEY_PRO=your-2.5-models-key

TOKEN_LIMIT = 100000  # Max tokens to process from input file
MAX_RETRIES = 3  # Max API retry attempts
RETRY_DELAY = 5  # Seconds to wait between retries

# Configure Tesseract OCR path
pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD",
    r"D:\Tesseract\tesseract.exe"
)
# Superscript mapping for LaTeX to Unicode
SUPERSCRIPTS = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")

# Valid Bloom's taxonomy levels
VALID_BLOOMS_LEVELS = {
    "remember", "understand", "apply", 
    "analyze", "evaluate", "create",
    "knowledge", "comprehension", "application",
    "analysis", "evaluation", "synthesis"
}

def latex_to_readable_unicode(expr: str) -> str:
    """
    Convert LaTeX math expressions to readable Unicode format.
    Handles superscripts, fractions, roots, and common math symbols.
    """
    try:
        if not expr or not isinstance(expr, str):
            return expr
            
        # Handle superscripts
        expr = re.sub(r"\^{\s*([^\}]+)\s*}", lambda m: str(m.group(1)).translate(SUPERSCRIPTS), expr)
        expr = re.sub(r"\^([0-9+\-()=])", lambda m: m.group(1).translate(SUPERSCRIPTS), expr)
        
        # Handle fractions and roots
        expr = re.sub(r"\\frac\s*{([^}]+)}{([^}]+)}", r"(\1)/(\2)", expr)
        expr = re.sub(r"\\sqrt\s*{([^}]+)}", r"√(\1)", expr)
        expr = re.sub(r"\\sqrt\[([^\]]+)\]\s*{([^}]+)}", r"\1√(\2)", expr)
        
        # Replace common math symbols
        replacements = {
            r"\cdot": "·",
            r"\times": "×",
            r"\div": "÷",
            r"\pm": "±",
            r"\leq": "≤",
            r"\geq": "≥",
            r"\neq": "≠",
            r"\approx": "≈",
            r"\infty": "∞"
        }
        for latex, unicode in replacements.items():
            expr = expr.replace(latex, unicode)
            
        return expr
    except Exception as e:
        logger.error(f"Error converting LaTeX: {e}")
        return expr

def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from PDF or text file with OCR fallback.
    Supports both PDF and plain text files.
    Logs character count and OCR usage.
    """
    try:
        logger.info(f"Extracting text from file: {file_path}")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
            
        text = ""
        used_ocr = False
        
        if file_path.endswith(".pdf"):
            try:
                with fitz.open(file_path) as doc:
                    text = "".join(page.get_text() for page in doc)
                    
                    # Use OCR if text extraction seems insufficient
                    if len(text.strip()) < 100 or "�" in text:
                        logger.info("Text extraction insufficient, using OCR for text extraction.")
                        used_ocr = True
                        text = ""
                        for page in doc:
                            pix = page.get_pixmap()
                            img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            img = img.convert("L")  # Convert to grayscale
                            text += pytesseract.image_to_string(img, lang="eng", config="--psm 6")
            except Exception as e:
                logger.error(f"PDF extraction error: {e}")
                return f"Error extracting PDF: {e}"
                
        elif file_path.endswith(".txt"):
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as file:
                    text = file.read()
            except Exception as e:
                logger.error(f"Text file reading error: {e}")
                return f"Error reading text file: {e}"
        else:
            raise ValueError("Unsupported file format. Only PDF and TXT files are supported.")
        
        # Limit text to TOKEN_LIMIT tokens
        tokens = text.split()
        if len(tokens) > TOKEN_LIMIT:
            text = " ".join(tokens[:TOKEN_LIMIT])
            logger.info(f"Text truncated to {TOKEN_LIMIT} tokens.")
        
        logger.info(f"Extracted text character count: {len(text)}")
        if used_ocr:
            logger.info("OCR was used for text extraction.")
        else:
            logger.info("OCR was NOT used for text extraction.")
            
        return text.strip()
    except Exception as e:
        logger.error(f"General extraction error: {e}")
        return f"Error extracting text: {e}"

def save_to_excel(data: List[List[Union[str, int]]], excel_path: str) -> bool:
    """
    Save question bank data to Excel with proper formatting and styling.
    Uses optimized saving method to prevent corruption.
    """
    try:
        logger.info(f"Saving question bank to Excel: {excel_path}")
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(excel_path) or ".", exist_ok=True)
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Question Bank"

        headers = [
            "Grade", "Subject", "Topic", "Question Type", 
            "Board", "Blooms Level", "Marks", "Question", "Options"
        ]
        ws.append(headers)

        # Style headers
        header_font = Font(bold=True, size=12)
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        for col in ws.iter_cols(min_row=1, max_row=1, min_col=1, max_col=len(headers)):
            for cell in col:
                cell.font = header_font
                cell.alignment = header_alignment

        # Write data rows
        for row_data in data:
            formatted_row = []
            for value in row_data:
                if isinstance(value, (list, tuple)):
                    value = ", ".join(str(v) for v in value)
                elif value is None:
                    value = ""
                formatted_row.append(str(value))
            ws.append(formatted_row)

        # Apply LaTeX conversion to Question and Options columns
        for row in ws.iter_rows(min_row=2):
            for cell in [row[7], row[8]]:  # Question and Options columns
                if cell.value and "$" in cell.value:
                    cell.value = latex_to_readable_unicode(cell.value)

        # Set column widths and row heights
        for col_idx, col in enumerate(ws.columns, 1):
            max_length = 0
            column = get_column_letter(col_idx)
            
            # Find longest content in column
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
                
            # Set column width (with limits)
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column].width = adjusted_width
            
            # Set all cells to wrap text
            for cell in col:
                cell.alignment = Alignment(wrap_text=True, vertical='top')

        # Optimize worksheet settings
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.outlinePr.summaryBelow = False
        
        # Save with optimization settings
        wb.save(excel_path, as_template=False)
        logger.info(f"Excel file successfully saved to {excel_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving Excel file: {e}\n{traceback.format_exc()}")
        return False

def normalize_blooms_levels(blooms_levels: Union[str, List[str], None]) -> List[str]:
    """
    Normalize and validate Bloom's taxonomy levels.
    Returns a list of valid Bloom's levels in capitalized form.
    """
    if not blooms_levels:
        return []
        
    if isinstance(blooms_levels, str):
        # Split comma-separated string
        levels = [x.strip() for x in blooms_levels.split(",") if x.strip()]
    elif isinstance(blooms_levels, (list, tuple)):
        levels = [str(x).strip() for x in blooms_levels if x]
    else:
        levels = [str(blooms_levels).strip()]
        
    # Validate and capitalize Bloom's levels
    normalized = []
    for level in levels:
        lower_level = level.lower()
        if any(vl in lower_level for vl in VALID_BLOOMS_LEVELS):
            # Capitalize first letter
            normalized.append(level.capitalize())
        else:
            logger.warning(f"Unrecognized Bloom's level '{level}'. Including anyway.")
            normalized.append(level)
            
    return normalized

def generate_questions_batched(
    grade: str,
    subject: str,
    topic: str,
    question_types: List[str],
    marks_map: dict,
    count_map: dict,
    board: str,
    blooms_levels: List[str],
    syllabus_text: Optional[str] = None,
    custom_prompt: str = ""
) -> Tuple[List[str], List[str], List[str], List[int]]:
    """
    OPTIMIZED: Generate ALL questions in a single API call for efficiency.
    This reduces API calls, token usage, and respects rate limits better.
    Especially important for Gemini 2.5 models.
    """
    try:
        logger.info(f"Generating questions for Grade {grade} {subject} ({board}) - BATCHED MODE")
        blooms_levels = normalize_blooms_levels(blooms_levels)
        if not blooms_levels:
            blooms_levels = ["Apply", "Analyze", "Evaluate"]
            logger.info("Using default Bloom's levels as none were specified")
        
        blooms_str = ", ".join(blooms_levels)
        
        # Build comprehensive prompt for all question types at once
        total_questions = sum(count_map.values())
        
        # Create detailed breakdown for each question type
        question_breakdown = []
        for qtype in question_types:
            count = count_map.get(qtype, 1)
            marks = marks_map.get(qtype, 1)
            question_breakdown.append(f"- {count} {qtype} questions worth {marks} marks each")
        
        breakdown_text = "\n".join(question_breakdown)
        
        # Comprehensive single prompt
        prompt = f"""Generate exactly {total_questions} questions for {board} {grade} grade {subject} on the topic of {topic}.

QUESTION BREAKDOWN REQUIRED:
{breakdown_text}

REQUIREMENTS:
- Use Bloom's taxonomy levels: {blooms_str}
- Each question must indicate exactly one Bloom's level in square brackets at the end: [Bloom's Level]
- Use grade-appropriate language
- Generate questions that invoke critical thinking and problem-solving skills
- Use LaTeX math formatting between $ symbols like $E=mc^2$ when needed

FORMAT EACH QUESTION EXACTLY LIKE THIS:
Type: [Question Type]
Marks: [Marks]
Question: The question text [Bloom's Level]
Options: A) Option 1, B) Option 2, C) Option 3, D) Option 4 (only for MCQ, Matching, True/False; leave blank for others)

IMPORTANT NOTES:
- For MCQ, Matching, and True/False: Always provide real, meaningful options. Never use generic placeholders.
- For other question types: Leave Options blank
- Provide only the questions and options, no additional explanations or headers
- Generate the EXACT number of each question type as specified above"""

        if custom_prompt:
            prompt += f"\n\nUser Instructions (High Priority): {custom_prompt}"
        
        if syllabus_text and not syllabus_text.startswith("Error"):
            prompt += f"\n\nUse only this Syllabus Context as your knowledge base:\n{syllabus_text}"
        
        # Single API call for all questions
        logger.info(f"Making single API call for {total_questions} questions (EFFICIENT MODE)")
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = None
        last_error = None
        
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Batched API attempt {attempt+1}/{MAX_RETRIES}")
                response = model.generate_content(prompt)
                if response.text:
                    logger.info("Batched API response received successfully")
                    break
            except Exception as api_error:
                last_error = api_error
                logger.warning(f"Batched API attempt {attempt+1} failed: {str(api_error)}")
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                continue
        
        if not response or not response.text:
            error_msg = last_error if last_error else "No response text generated by the model"
            logger.error(f"Failed to generate questions in batched mode: {error_msg}")
            # Fallback to individual calls if batched fails
            logger.info("Falling back to individual question generation...")
            return generate_questions_individual(grade, subject, topic, question_types, marks_map, count_map, board, blooms_levels, syllabus_text, custom_prompt)
        
        # Parse the batched response
        questions, options, types, marks_list = [], [], [], []
        current_question = None
        current_type = None
        current_marks = None
        
        for line in response.text.split("\n"):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("Type:"):
                current_type = line.replace("Type:", "").strip()
            elif line.startswith("Marks:"):
                try:
                    current_marks = int(line.replace("Marks:", "").strip().strip("[]"))
                except ValueError:
                    current_marks = 1
            elif line.startswith("Question:"):
                current_question = line.replace("Question:", "").strip()
            elif line.startswith("Options:"):
                current_options = line.replace("Options:", "").strip()
                
                # Save the complete question
                if current_question and current_type:
                    questions.append(current_question)
                    options.append(current_options)
                    types.append(current_type)
                    marks_list.append(current_marks or 1)
                
                # Reset for next question
                current_question = None
                current_type = None
                current_marks = None
        
        # Handle case where last question doesn't have options line
        if current_question and current_type:
            questions.append(current_question)
            options.append("")  # No options for non-MCQ types
            types.append(current_type)
            marks_list.append(current_marks or 1)
        
        logger.info(f"Successfully generated {len(questions)} questions in batched mode")
        return questions, options, types, marks_list
        
    except Exception as e:
        logger.error(f"Error in batched question generation: {e}")
        # Fallback to individual generation
        logger.info("Falling back to individual question generation due to error...")
        return generate_questions_individual(grade, subject, topic, question_types, marks_map, count_map, board, blooms_levels, syllabus_text, custom_prompt)

def generate_questions(
    grade: str,
    subject: str,
    topic: str,
    question_types: List[str],
    marks_map: dict,
    count_map: dict,
    board: str,
    blooms_levels: List[str],
    syllabus_text: Optional[str] = None,
    custom_prompt: str = ""
) -> Tuple[List[str], List[str], List[str], List[int]]:
    """
    SMART DISPATCHER: Chooses between batched and individual generation.
    Uses batched mode for Gemini 2.5 models (more efficient).
    Falls back to individual mode for other models or if batched fails.
    """
    try:
        # Check if we should use batched mode (for 2.5 models and multiple question types)
        use_batched = (
            "2.5" in GEMINI_MODEL and 
            len(question_types) > 1 and 
            sum(count_map.values()) > 3
        )
        
        if use_batched:
            logger.info(f"Using BATCHED mode for {GEMINI_MODEL} (efficient for rate limits)")
            return generate_questions_batched(grade, subject, topic, question_types, marks_map, count_map, board, blooms_levels, syllabus_text, custom_prompt)
        else:
            logger.info(f"Using INDIVIDUAL mode for {GEMINI_MODEL}")
            return generate_questions_individual(grade, subject, topic, question_types, marks_map, count_map, board, blooms_levels, syllabus_text, custom_prompt)
    
    except Exception as e:
        logger.error(f"Error in question generation dispatcher: {e}")
        # Final fallback to individual mode
        return generate_questions_individual(grade, subject, topic, question_types, marks_map, count_map, board, blooms_levels, syllabus_text, custom_prompt)

def generate_questions_individual(
    grade: str,
    subject: str,
    topic: str,
    question_types: List[str],
    marks_map: dict,
    count_map: dict,
    board: str,
    blooms_levels: List[str],
    syllabus_text: Optional[str] = None,
    custom_prompt: str = ""
) -> Tuple[List[str], List[str], List[str], List[int]]:
    """
    FALLBACK: Generate questions individually (one API call per question type).
    Used when batched generation fails or for older models.
    """
    try:
        logger.info(f"Generating questions for Grade {grade} {subject} ({board})")
        blooms_levels = normalize_blooms_levels(blooms_levels)
        if not blooms_levels:
            blooms_levels = ["Apply", "Analyze", "Evaluate"]
            logger.info("Using default Bloom's levels as none were specified")
        blooms_str = ", ".join(blooms_levels)

        all_questions: List[str] = []
        all_options: List[str] = []
        all_types: List[str] = []
        all_marks: List[int] = []

        for qtype in question_types:
            n = count_map.get(qtype, 1)
            marks = marks_map.get(qtype, 1)

            prompt = f"""Generate exactly {n} {qtype} questions for {board} {grade} grade {subject} on the topic of {topic}.
Each question must be worth {marks} marks. Use Bloom's taxonomy levels: {blooms_str}.
For each question, indicate exactly one specific Bloom's level in square brackets at the very end like this: [Bloom's Level].
Do not include any other information in brackets.
Use grade appropriate language.
Generate questions that invoke critical thinking and problem-solving skills.
Format each question exactly like this:
- Type: [Question Type]
- Marks: [Marks]
- Question: The question text [Bloom's Level]
- Options: A) Option 1, B) Option 2, C) Option 3, D) Option 4 (only if question type is MCQ, Matching, or True/False; leave blank otherwise)
- For MCQ, Matching, and True/False, always provide real, meaningful options. Never use generic placeholders like "Option 1", "Option 2", etc.
Use LaTeX math formatting between $ symbols like $E=mc^2$ when needed.
Provide only the questions and options, no additional explanations or headers."""

            if custom_prompt:
                prompt += f"\n\nUser Instructions (High Priority): {custom_prompt}"
            if syllabus_text and not syllabus_text.startswith("Error"):
                prompt += f"\n\nUse only this Syllabus Context as your knowledge base:\n{syllabus_text}"

            model = genai.GenerativeModel(GEMINI_MODEL)
            response = None
            last_error: Optional[Exception] = None

            for attempt in range(MAX_RETRIES):
                try:
                    logger.info(f"API attempt {attempt+1}/{MAX_RETRIES} for {qtype} question generation")
                    response = model.generate_content(prompt)
                    if response and response.text:
                        logger.info("API response received successfully")
                        break
                except Exception as e:
                    last_error = e
                    logger.warning(f"API attempt {attempt+1} failed: {str(e)}")
                    if attempt < MAX_RETRIES - 1:
                        logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                        time.sleep(RETRY_DELAY)

            if not response or not getattr(response, 'text', None):
                error_msg = str(last_error) if last_error else "No response text generated by the model"
                logger.error(f"Failed to generate questions for type {qtype}: {error_msg}")
                continue

            # Parse response lines
            questions: List[str] = []
            options: List[str] = []
            types: List[str] = []
            marks_list: List[int] = []

            current_question: Optional[str] = None
            current_type: Optional[str] = None
            current_marks: Optional[int] = None

            for raw_line in response.text.split("\n"):
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("- Type:"):
                    current_type = line.replace("- Type:", "").strip()
                elif line.startswith("- Marks:"):
                    try:
                        current_marks = int(line.replace("- Marks:", "").strip().strip("[]"))
                    except Exception:
                        current_marks = marks
                elif line.startswith("- Question:"):
                    current_question = line.replace("- Question:", "").strip()
                    questions.append(current_question)
                    types.append(current_type if current_type else qtype)
                    marks_list.append(current_marks if current_marks is not None else marks)
                    options.append("")
                elif line.startswith("- Options:"):
                    if questions:
                        options[-1] = line.replace("- Options:", "").strip()

            # Ensure marks are set for all questions
            for i, t in enumerate(types):
                if not marks_list[i]:
                    marks_list[i] = int(marks_map.get(t, marks) or marks)

            all_questions.extend(questions)
            all_options.extend(options)
            all_types.extend(types)
            all_marks.extend(marks_list)

        return all_questions, all_options, all_types, all_marks
    except Exception as e:
        logger.error(f"Error generating questions: {e}\n{traceback.format_exc()}")
        return [], [], [], []

def generate_question_bank(
    grade: str,
    subject: str,
    topic: str,
    question_types: Union[str, List[str]],
    marks_map: dict,
    count_map: dict,
    num_questions: int,
    board: str,
    blooms_levels: Union[str, List[str]],
    syllabus_path: Optional[str] = None,
    custom_prompt: str = "",
    include_images: bool = False,
    export_format: str = "excel"
) -> str:
    """
    Main function to generate question bank Excel file.
    Returns path to generated Excel file.
    - Supports multiple question types (MCQ, Short/Long Answer, Fill in the Blanks, Matching, True/False)
    - Ensures proper column order and formatting
    - Handles LaTeX to Unicode conversion for readability
    - Robust error handling and logging
    - Accepts a mapping of {question_type: marks} and {question_type: num_questions}
    - If include_images is True, generates images for questions that require diagrams and adds an 'AI Image' column.
    """
    try:
        logger.info(f"Starting question bank generation for Grade {grade} {subject}")
        logger.info(f"Using model: {GEMINI_MODEL}")
        blooms_levels = normalize_blooms_levels(blooms_levels)
        if not blooms_levels:
            blooms_levels = ["Apply", "Analyze", "Evaluate"]
            logger.info("Using default Bloom's levels as none were specified")
        syllabus_text = None
        if syllabus_path and os.path.exists(syllabus_path):
            syllabus_text = extract_text_from_file(syllabus_path)
            if syllabus_text.startswith("Error"):
                raise ValueError("The syllabus could not be read. Check the source before generating questions.")
        if isinstance(question_types, str):
            question_types = [question_types]
        questions, options, types, marks = generate_questions(
            grade, subject, topic, question_types, marks_map, count_map, board, blooms_levels, syllabus_text, custom_prompt
        )
        if not questions:
            raise ValueError("No questions were generated. Please check your inputs and try again.")
        if len(questions) != num_questions or not (len(questions) == len(options) == len(types) == len(marks)):
            raise ValueError("The model did not return the requested question count. Generation stopped.")
        from collections import Counter
        clean_types = [str(t).strip().strip('[]') for t in types]
        if Counter(clean_types) != Counter({t: count_map[t] for t in question_types}):
            raise ValueError("Generated question types do not match the requested allocation.")
        if any(int(mark) != int(marks_map[qtype]) for qtype, mark in zip(clean_types, marks)):
            raise ValueError("Generated question marks do not match the requested allocation.")
        data = []
        image_paths = []
        for idx, (question, option, qtype, mark) in enumerate(zip(questions, options, types, marks)):
            blooms_level = "Unknown"
            question_text = question
            bloom_match = re.search(r"\[([^\]]+)\]$", question_text)
            if bloom_match:
                blooms_level = bloom_match.group(1).strip()
                question_text = re.sub(r"\s*\[[^\]]+\]$", "", question_text).strip()
            clean_qtype = str(qtype).strip()
            if clean_qtype.startswith("[") and clean_qtype.endswith("]"):
                clean_qtype = clean_qtype[1:-1].strip()
            clean_qtype_lower = clean_qtype.lower().replace(" ", "")
            is_options_type = any(
                kw in clean_qtype_lower
                for kw in ["mcq", "multiplechoice", "matching", "true/false", "truefalse", "trueorfalse"]
            )
            if is_options_type and not option.strip():
                raise ValueError(f"Missing answer options for a {clean_qtype} question. Generation stopped.")
            # Image generation logic
            image_path = ""
            needs_diagram = "[DIAGRAM REQUIRED]" in question.upper() or "diagram" in question.lower()
            
            if include_images and needs_diagram:
                logger.info(f"[IMAGE] Image generation enabled for question {idx + 1}: {question_text[:50]}...")
                try:
                    from imagen import generate_diagram_image
                    import hashlib
                    q_hash = hashlib.md5(question_text.encode('utf-8')).hexdigest()[:10]
                    image_filename = f"diagram_{q_hash}.png"
                    image_full_path = os.path.join("uploads", image_filename)
                    
                    # Enhanced prompt for better diagram generation
                    prompt = f"Generate a clean, contextually accurate diagram or illustration relevant to the following question for a school exam paper. Do NOT include any text, labels, or explanations in the image, except for essential diagram indicators (such as A, B, 1, 2, etc.), mathematical symbols, or blank lines. Only draw the diagram or illustration itself.\nQuestion: {question_text}"
                    
                    if not os.path.exists(image_full_path):
                        logger.info(f"[GEN] Generating image for question {idx + 1}...")
                        result = generate_diagram_image(prompt, output_filename=image_full_path)
                        if result and os.path.exists(image_full_path):
                            logger.info(f"[OK] Image generated successfully: {image_filename}")
                            image_path = image_full_path
                        else:
                            logger.error(f"[ERROR] Image generation failed for question {idx + 1}")
                            image_path = ""
                    else:
                        logger.info(f"[INFO] Image already exists: {image_filename}")
                        image_path = image_full_path
                        
                    # Verify image file integrity
                    if image_path and os.path.exists(image_path):
                        try:
                            from PIL import Image
                            with Image.open(image_path) as img:
                                img.verify()
                            logger.info(f"[VERIFY] Image integrity verified: {image_filename}")
                        except Exception as img_error:
                            logger.warning(f"[WARN] Image integrity check failed: {img_error}")
                            # Remove corrupted image
                            try:
                                os.remove(image_path)
                                image_path = ""
                            except:
                                pass
                                
                except Exception as e:
                    logger.error(f"[ERROR] Image generation failed for question {idx + 1}: {question_text[:50]}... | Error: {e}")
                    image_path = ""
            elif needs_diagram and not include_images:
                logger.info(f"[INFO] Question {idx + 1} needs diagram but image generation is disabled")
            else:
                logger.debug(f"[DEBUG] Question {idx + 1} does not require diagram")
            image_paths.append(image_path)
            row = [
                str(grade),
                subject,
                topic,
                clean_qtype,
                board,
                blooms_level,
                float(mark) if isinstance(mark, (int, float)) else str(mark),
                question_text,
                option.strip() if is_options_type else ""
            ]
            # Attach AI image path directly so it stays aligned across sorting
            if include_images:
                row.append(image_path)
            data.append(row)
        # Sort data by question type (column index 3)
        data.sort(key=lambda row: (row[3] or "").lower())
        # Add AI Image column if enabled
        headers = [
            "Grade", "Subject", "Topic", "Question Type", "Board", "Blooms Level", "Marks", "Question", "Options"
        ]
        if include_images:
            headers.append("AI Image")
        # Generate safe filename
        safe_subject = re.sub(r'[\\/*?:"<>|]', "", subject)
        safe_topic = re.sub(r'[\\/*?:"<>|]', "", topic)
        excel_filename = secure_filename(f"Grade{grade}_{safe_subject}_{safe_topic}_question_bank.xlsx")
        excel_path = os.path.join("uploads", excel_filename)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(excel_path) or ".", exist_ok=True)
        
        # Create workbook with optimized settings
        wb = Workbook()
        ws = wb.active
        ws.title = "Question Bank"
        
        # Define headers
        headers = [
            "Grade", "Subject", "Topic", "Question Type", 
            "Board", "Blooms Level", "Marks", "Question", "Options"
        ]
        if include_images:
            headers.append("AI Image")
            
        ws.append(headers)
        
        # Style headers
        header_font = Font(bold=True, size=12)
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        for col in ws.iter_cols(min_row=1, max_row=1, min_col=1, max_col=len(headers)):
            for cell in col:
                cell.font = header_font
                cell.alignment = header_alignment

        # Add data rows
        for row_data in data:
            ws.append(row_data)
            
        # Set column widths and formatting
        for col_idx, col in enumerate(ws.columns, 1):
            max_length = 0
            column = get_column_letter(col_idx)
            
            # Find longest content in column
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
                
            # Set column width (with limits)
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column].width = adjusted_width
            
            # Set all cells to wrap text
            for cell in col:
                cell.alignment = Alignment(wrap_text=True, vertical='top')

        # Save based on export format
        if export_format == "word":
            # Generate Word document
            word_path = excel_path.replace('.xlsx', '.docx')
            from docx import Document
            from docx.shared import Inches
            document = Document()
            document.add_heading(f"Grade {grade} {subject}: {topic}", 0)
            for number, row in enumerate(data, 1):
                document.add_paragraph(f"{number}. {row[7]} [{row[6]} marks]")
                if row[8]:
                    document.add_paragraph(str(row[8]))
                if include_images and len(row) > 9 and row[9] and os.path.isfile(row[9]):
                    document.add_picture(row[9], width=Inches(4.5))
            document.save(word_path)
            return word_path
        else:
            # Save Excel with embedded images if enabled
            if include_images:
                try:
                    logger.info("[IMAGE] Embedding images into Excel cells (AI Image column)")
                    # Determine AI Image column index based on headers used above
                    ai_col_idx = None
                    for idx, header_cell in enumerate(ws[1], start=1):
                        if str(header_cell.value).strip().lower() == "ai image":
                            ai_col_idx = idx
                            break
                    if ai_col_idx:
                        # Standardized image max size
                        MAX_W, MAX_H = 240, 140
                        col_letter = get_column_letter(ai_col_idx)
                        for row_idx in range(2, ws.max_row + 1):
                            cell = ws.cell(row=row_idx, column=ai_col_idx)
                            img_path = str(cell.value).strip() if cell.value else ""
                            if img_path and os.path.exists(img_path):
                                try:
                                    img = XLImage(img_path)
                                    # Compute scale to fit BOTH width and height constraints
                                    scale_w = MAX_W / float(img.width or MAX_W)
                                    scale_h = MAX_H / float(img.height or MAX_H)
                                    scale = min(scale_w, scale_h, 1.0)
                                    img.width = int((img.width or MAX_W) * scale)
                                    img.height = int((img.height or MAX_H) * scale)
                                    anchor = f"{col_letter}{row_idx}"
                                    ws.add_image(img, anchor)
                                    cell.value = ""
                                    # Fit row height for consistent visual size
                                    ws.row_dimensions[row_idx].height = max(ws.row_dimensions[row_idx].height or 15, MAX_H)
                                except Exception as ie:
                                    logger.warning(f"[WARN] Failed to embed image at row {row_idx}: {ie}")
                    else:
                        logger.warning("AI Image column not found; saving paths as text")
                except Exception as e:
                    logger.error(f"[ERROR] Error while embedding images into Excel: {e}")
            # Save workbook
            wb.save(excel_path)
        logger.info(f"Question bank generated successfully: {excel_path}")
        return excel_path
        
    except Exception as e:
        logger.error(f"Error in generate_question_bank: {e}\n{traceback.format_exc()}")
        return ""