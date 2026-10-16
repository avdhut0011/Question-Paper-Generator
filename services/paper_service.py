import os
from flask import current_app
from werkzeug.utils import secure_filename
import re
import logging
import traceback
from datetime import datetime
from typing import Optional, List, Tuple
import hashlib
import time

from config import UPLOAD_DIR, logger
from services.ai_service import generate_questions_for_paper, select_questions_from_bank_with_ai
from services.question_service import (
    format_questions,
    load_question_bank,
)
from services.latex_service import (
    compile_latex_to_pdf,
    fix_invalid_siunitx_units,
    fix_split_latex_commands,
    fix_split_siunitx_macros,
    fix_siunitx_braces,
    sanitize_latex_macros,
    escape_latex_special_chars,
    remove_double_backslashes_in_text,
    clean_siunitx_units,
    enhanced_latex_processing,
)
from services.preview_service import generate_html_preview
from paper_layouts.paper_templates import (
    get_aus_paper_template,
    get_aga_paper_template,
    get_default_paper_template,
)

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


def extract_text_from_pdf(path: str) -> str:
    """Extract reference text; reject failed required sources rather than ignoring them."""
    if path.lower().endswith('.txt'):
        return open(path, encoding='utf-8-sig').read()
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


def generate_question_paper(
    grade: str,
    subject: str,
    total_marks: int,
    difficulty_split: dict,
    num_questions: int,
    board: str,
    blooms_levels: list,
    custom_instructions: str,
    syllabus_path: Optional[str] = None,
    sample_path: Optional[str] = None,
    include_images: bool = True,
    question_bank_path: Optional[str] = None,
    use_question_bank_only: bool = False,
    paper_template: str = "default",
    blueprint_path: Optional[str] = None
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Main function to generate question paper with comprehensive error handling and image support."""
    logger.info(f"Starting question paper generation for {subject} (Grade {grade})")
    paper_text = ""
    try:
        # Determine the source of questions
        if use_question_bank_only:
            # Enhanced logic for using an existing question bank with AI selection
            if not question_bank_path or not os.path.exists(question_bank_path):
                return None, None, None, "Question bank file not found or path is invalid."
            logger.info(f"Loading questions from bank: {question_bank_path}")
            questions = load_question_bank(question_bank_path)
            if not questions:
                return None, None, None, "No questions found in the provided question bank file. Ensure questions are in column 'H' and options in column 'I'."
            if len(questions) < num_questions:
                return None, None, None, f"Not enough questions in the bank ({len(questions)}) to meet the requirement of {num_questions} questions."
            
            # Extract blueprint text if provided
            blueprint_text = None
            if blueprint_path and os.path.exists(blueprint_path):
                blueprint_text = extract_text_from_pdf(blueprint_path)
                logger.info("Paper blueprint loaded for AI question selection")
            
            # Use AI to intelligently select questions from the bank
            paper_text = select_questions_from_bank_with_ai(
                questions, num_questions, grade, subject, total_marks, 
                difficulty_split, board, blooms_levels, custom_instructions, 
                blueprint_text
            )
            syllabus_text = None
            sample_text = None
        else:
            # Logic for generating questions with AI
            logger.info("Generating questions using AI model.")
            syllabus_text = None
            if syllabus_path and os.path.exists(syllabus_path):
                syllabus_text = extract_text_from_pdf(syllabus_path)
            sample_text = None
            if sample_path and os.path.exists(sample_path):
                sample_text = extract_text_from_pdf(sample_path)

            if blueprint_path and os.path.exists(blueprint_path):
                blueprint_text = extract_text_from_pdf(blueprint_path)
                sample_text = (sample_text or '') + '\nPaper blueprint:\n' + blueprint_text
            for reference in (syllabus_text, sample_text):
                if reference and reference.startswith('Error'):
                    raise ValueError('A reference could not be read. Check the uploaded source.')
            paper_text = generate_questions_for_paper(
                grade, subject, total_marks, difficulty_split, num_questions, board,
                blooms_levels, custom_instructions, syllabus_text, sample_text
            )
    except Exception as e:
        logger.error(f"Error during question sourcing: {e}\n{traceback.format_exc()}")
        return None, None, None, f"An unexpected error occurred: {e}"

    if not paper_text or "Error" in paper_text:
        logger.error("Question generation failed or returned an error.")
        return None, None, None, paper_text or "Failed to generate question content."

    from services.question_service import _parse_paper_text_to_questions, extract_metadata
    blocks = _parse_paper_text_to_questions(paper_text)
    if len(blocks) != num_questions or sum(int(extract_metadata(q)['marks']) for q in blocks) != total_marks:
        return None, None, None, 'Generated question count or marks do not match your request. Generation stopped; please retry.'
    from school_platform.validation import fingerprint
    stems = [fingerprint(extract_metadata(q)['clean_text']) for q in blocks]
    if len(set(stems)) != len(stems):
        return None, None, None, 'The generated paper contains duplicate questions. Generation stopped.'
    if use_question_bank_only:
        def bank_signature(question):
            question = re.sub(r'^(?:Question\s*)?\d+[.):]\s*', '', question.strip(), flags=re.IGNORECASE)
            question = re.sub(r'\[(Remember|Understand|Apply|Analyze|Evaluate|Create)\]', '', question, flags=re.IGNORECASE)
            return re.sub(r'\s+', '', question).casefold()
        available = {bank_signature(question) for question in questions}
        if any(bank_signature(question) not in available for question in blocks):
            return None, None, None, 'The AI changed a question outside the uploaded bank. Generation stopped; please retry.'
    # --- LaTeX and Preview Generation ---
    try:
        # Format and post-process only the questions, not the preamble
        formatted_questions = format_questions(paper_text, include_images=include_images, subject=subject, grade=grade)
        # Questions are escaped once by the formatter. Running the old generic
        # cleaners again corrupts math delimiters and comments out list commands.
        date_str = datetime.today().strftime("%B %d, %Y")
        time_str = datetime.today().strftime("%I:%M %p")
        
        from school_platform.rendering import escape_plain
        safe_grade, safe_subject = escape_plain(grade), escape_plain(subject)
        # Select template based on paper_template parameter
        if paper_template == "aus":
            tex_template = get_aus_paper_template(safe_grade, safe_subject, total_marks, date_str, time_str)
        elif paper_template == "aga":
            tex_template = get_aga_paper_template(safe_grade, safe_subject, total_marks, date_str, time_str)
        else:
            tex_template = get_default_paper_template(safe_grade, safe_subject, total_marks, date_str, time_str)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        tex_filename = secure_filename(f"Grade{grade}_{subject}_QP_{timestamp}.tex")
        tex_path = os.path.join(UPLOAD_DIR, tex_filename)
        pdf_path = tex_path.replace(".tex", ".pdf")
        with open(tex_path, "w", encoding="utf-8") as f:
            # Insert the sanitized questions into the template
            final_latex = tex_template.replace('<<QUESTIONS>>', formatted_questions)
            f.write(final_latex)
        logger.info(f"LaTeX file written: {tex_path}")
        # Compile LaTeX to PDF
        if current_app.config.get('REQUIRE_PDF', True):
            success, error_log = compile_latex_to_pdf(tex_path, pdf_path)
        else:
            success, error_log = True, None
        # Always generate preview_html, even if LaTeX fails
        preview_html = generate_html_preview(grade, subject, total_marks, date_str, paper_text, include_images=include_images)
        if not success:
            return None, tex_path, preview_html, error_log or "LaTeX compilation failed"
        return pdf_path if os.path.isfile(pdf_path) else None, tex_path, preview_html, None
    except Exception as e:
        logger.error(f"Error during LaTeX and preview generation: {e}\n{traceback.format_exc()}")
        return None, None, None, f"An unexpected error occurred during document generation: {e}"
