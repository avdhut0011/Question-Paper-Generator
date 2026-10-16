# qp_model.py
import os
import subprocess
import re
import logging
import traceback
import hashlib
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

from config import client, GENAI_AVAILABLE, GEMINI_MODEL, UPLOAD_DIR, logger, types, genai
from services.ai_service import generate_questions_for_paper, select_questions_from_bank_with_ai
from services.question_service import (
    extract_metadata,
    extract_table_data_from_question,
    _clean_mcq_format,
    _parse_paper_text_to_questions,
    format_mcq_question,
    process_question,
    format_questions,
    load_question_bank,
)
from services.latex_service import (
    LATEX_PACKAGES,
    LATEX_HEADER,
    compile_latex_to_pdf,
    _compile_latex_fallback,
    _compile_latex_minimal,
    _compile_latex_basic,
    fix_invalid_siunitx_units,
    fix_split_latex_commands,
    fix_split_siunitx_macros,
    fix_siunitx_braces,
    sanitize_latex_macros,
    escape_latex_special_chars,
    remove_double_backslashes_in_text,
    clean_siunitx_units,
    enhanced_latex_processing,
    generate_table_latex_from_question,
)
from services.preview_service import generate_html_preview
from paper_layouts.paper_templates import (
    get_aus_paper_template,
    get_aga_paper_template,
    get_default_paper_template,
)
from services.paper_service import generate_question_paper

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from imagen import generate_diagram_image
import pandas as pd

try:
    from google import genai as _genai
    from google.genai import types as _types
    GENAI_AVAILABLE = True
    genai = _genai
    types = _types
except Exception:
    try:
        import google.generativeai as _genai2
        GENAI_AVAILABLE = True
        genai = _genai2
        types = None
    except Exception:
        GENAI_AVAILABLE = False
        genai = None
        types = None

try:
    from pylatexenc.latexencode import unicode_to_latex
    LATEX_ENCODE_AVAILABLE = True
except Exception:
    LATEX_ENCODE_AVAILABLE = False
    def unicode_to_latex(text):
        return text
def extract_text_from_pdf(path: str) -> str:
    """Robust PDF text extraction with OCR fallback."""
    try:
        logger.info(f"Extracting text from PDF: {path}")
        doc = fitz.open(path)
        text = ""
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            try:
                page_text = page.get_text("text")  # type: ignore
            except Exception as e:
                logger.error(f"Text extraction error: {e}")
                page_text = ""
            if len(page_text.strip()) < 50:
                logger.debug(f"Page {page_num+1}: Using OCR for text extraction")
                try:
                    pix = page.get_pixmap(dpi=200)  # type: ignore
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    page_text = pytesseract.image_to_string(img, config='--psm 6')
                except Exception as e:
                    logger.error(f"PixMap/OCR error: {e}")
                    page_text = ""
            text += page_text + "\n"
        logger.info(f"Extracted {len(text)} characters from PDF")
        return text.strip()
    except Exception as e:
        logger.error(f"PDF extraction error: {e}\n{traceback.format_exc()}")
        return f"Error reading PDF: {e}"

# LaTeX processing functions relocated to services/latex_service.py and imported above.





# LaTeX table generation moved to services/latex_service.generate_table_latex_from_question

# Add a function to load and sample questions from an uploaded question bank (Excel/CSV)
def load_question_bank(filepath: str) -> List[str]:
    """
    Load questions from an Excel or CSV file.
    It reads 'Question' from column H, 'Options' from column I, and 'Marks' from column G.
    It robustly handles cases where the first MCQ option is attached to the question stem.
    """
    questions = []
    try:
        df = pd.read_excel(filepath) if filepath.endswith('.xlsx') else pd.read_csv(filepath)
        
        # Dynamically find column names or fall back to indices
        column_map = {
            'question': 'Question',
            'options': 'Options',
            'marks': 'Marks'
        }
        
        # Find actual column names in the dataframe, case-insensitive
        for key, default_name in column_map.items():
            found = False
            for col in df.columns:
                if default_name.lower() == col.lower():
                    column_map[key] = col
                    found = True
                    break
            if not found:
                # If a standard name isn't found, fallback to index
                if key == 'question': column_map[key] = df.columns[7] # H
                elif key == 'options': column_map[key] = df.columns[8] # I
                elif key == 'marks': column_map[key] = df.columns[6]   # G

        for index, row in df.iterrows():
            question_text = str(row.get(column_map['question'], '')).strip()
            options_text = str(row.get(column_map['options'], '')).strip()
            marks = row.get(column_map['marks'], 1)

            try:
                marks = int(marks) if pd.notna(marks) else 1
            except (ValueError, TypeError):
                marks = 1

            if not question_text:
                continue

            # Robustly find and detach the first MCQ option if it's attached to the question
            match = re.search(r'(?<!^)\s*([\[\(]?[A-Da-d][\]\)\.])', question_text)
            if match:
                split_index = match.start()
                first_option_part = question_text[split_index:].strip()
                question_text = question_text[:split_index].strip()
                options_text = f"{first_option_part} {options_text}".strip()

            # Format the question based on whether it has options
            if options_text:
                # This is an MCQ. Add metadata and format the options.
                final_question_str = f"[MULTIPLE CHOICE] {question_text} [{marks}]\n"
                
                # Split the full options string right before each option marker (e.g., "A)", "B)")
                option_lines = re.split(r'\s*(?=[\[\(]?[A-Da-d][\]\)\.])', options_text)
                
                for line in option_lines:
                    if line.strip():
                        final_question_str += f"{line.strip()}\n"
                
                questions.append(final_question_str.strip())
            else:
                # This is a regular (non-MCQ) question.
                questions.append(f"{question_text} [{marks}]")
                
    except Exception as e:
        logger.error(f"Error loading question bank from {filepath}: {e}\n{traceback.format_exc()}")
        return []
        
    return questions

