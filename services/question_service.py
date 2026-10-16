"""Question-related services moved from qp_model.py.
Contains parsing, formatting, and question-bank loading helpers.
Do not modify logic; imports adjusted to avoid circular imports.
"""
import os
import re
import time
import hashlib
from typing import Optional, List, Tuple
import traceback

from config import UPLOAD_DIR, logger
from school_platform.rendering import latex_text as latex_escape
from imagen import generate_diagram_image
import pytesseract
from PIL import Image
import pandas as pd


def extract_metadata(question: str) -> dict:
    """Extract marks and special requirements from question text."""
    logger.debug("Extracting question metadata")
    marks_match = re.search(r'\[(\d+)\]', question)
    marks = marks_match.group(1) if marks_match else "0"
    
    needs_diagram = "[DIAGRAM REQUIRED]" in question.upper()
    needs_table = "[TABLE REQUIRED]" in question.upper()
    is_mcq = "[MULTIPLE CHOICE]" in question.upper()
    
    blooms_level = None
    blooms_keywords = ["remember", "understand", "apply", "analyze", "evaluate", "create", "synthesize"]
    for keyword in blooms_keywords:
        if f"[{keyword.upper()}]" in question.upper():
            blooms_level = keyword.capitalize()
            break
    
    clean_question = re.sub(r'\s*\[\d+\]\s*', '', question).strip()
    clean_question = re.sub(r'\[DIAGRAM REQUIRED\]', '', clean_question, flags=re.IGNORECASE).strip()
    clean_question = re.sub(r'\[TABLE REQUIRED\]', '', clean_question, flags=re.IGNORECASE).strip()
    clean_question = re.sub(r'\[MULTIPLE CHOICE\]', '', clean_question, flags=re.IGNORECASE).strip()
    if blooms_level:
        clean_question = re.sub(rf'\[{blooms_level.upper()}\]', '', clean_question, flags=re.IGNORECASE).strip()
    
    return {
        "clean_text": clean_question,
        "marks": marks,
        "needs_diagram": needs_diagram,
        "needs_table": needs_table,
        "is_mcq": is_mcq,
        "blooms_level": blooms_level
    }


def extract_table_data_from_question(question_text: str) -> Tuple[str, str]:
    """Extracts markdown or whitespace-separated table data from the lines after the main question."""
    lines = question_text.split('\n')
    table_lines = []
    non_table_lines = []
    in_table = False
    for line in lines:
        # Markdown table or whitespace-separated table
        if re.match(r'^\s*\|.*\|\s*$', line) or re.match(r'^\s*\|?\s*-+\s*\|', line) or re.match(r'^\s*([\w\d\-]+\s+)+[\w\d\-]+\s*$', line):
            table_lines.append(line)
            in_table = True
        elif in_table and (line.strip() == '' or re.match(r'^\s*$', line)):
            # End of table
            in_table = False
        elif in_table:
            table_lines.append(line)
        else:
            non_table_lines.append(line)
    table_data = '\n'.join(table_lines).strip()
    cleaned_question = '\n'.join(non_table_lines).strip()
    return cleaned_question, table_data


def _clean_mcq_format(question_text: str) -> str:
    """
    Ensures the first option of an MCQ is on a new line.
    e.g., '...question?A) option' -> '...question?\nA) option'
    """
    if "[MULTIPLE CHOICE]" not in question_text.upper():
        return question_text

    # This pattern looks for the end of a question stem (e.g., a '?' or a metadata tag like '[5]')
    # followed by whitespace that does NOT contain a newline,
    # and then an option marker (like 'A)', '(B)', or 'C.').
    pattern = re.compile(
        r'([\?\]])'                  # Group 1: The end of the question stem (a '?' or ']')
        r'(\s*)'                     # Group 2: Whitespace
        r'([\[\(]?[A-Da-d][\]\)\.])' # Group 3: The option marker
    )

    match = pattern.search(question_text)

    # If a match is found and there's no newline between the stem and the first option, insert one.
    if match and '\n' not in match.group(2):
        # Replaces '] A)' with ']\nA)'
        return pattern.sub(r'\1\n\2\3', question_text, count=1)

    return question_text


def _parse_paper_text_to_questions(paper_text: str) -> List[str]:
    """
    Parses a raw string of questions into a list of individual questions.
    Handles multi-line questions, especially MCQs.
    """
    questions: List[str] = []
    current_question_lines: List[str] = []
    # Split by newline and filter out empty lines
    lines = [line.strip() for line in paper_text.strip().split('\n') if line.strip()]

    for line in lines:
        # Heuristic to detect start of a new question: presence of marks or metadata tags.
        is_new_question_heuristic = (
            re.search(r'\[\d+\]', line) or
            "[DIAGRAM REQUIRED]" in line.upper() or
            "[TABLE REQUIRED]" in line.upper() or
            "[MULTIPLE CHOICE]" in line.upper()
        )
        
        # An MCQ option line (e.g., "A) ...", "(B)...") should not start a new question.
        is_mcq_option = re.match(r'^\s*([\[\(]?[A-Da-d][\]\)\.])', line)

        # A line is considered the start of a new question if it has question-like metadata
        # AND it is not an MCQ option line.
        if is_new_question_heuristic and not is_mcq_option:
            if current_question_lines:
                question_block = '\n'.join(current_question_lines)
                questions.append(_clean_mcq_format(question_block))
            current_question_lines = [line]
        else:
            current_question_lines.append(line)
            
    # Add the last assembled question to the list
    if current_question_lines:
        question_block = '\n'.join(current_question_lines)
        questions.append(_clean_mcq_format(question_block))
        
    return questions


def format_mcq_question(question_text: str) -> str:
    """Format multiple choice questions with proper LaTeX."""
    logger.debug("Formatting MCQ question")
    parts = question_text.split('\n')
    stem = parts[0].strip()
    options = []

    # Accept A), A., [A], etc., but never A\)
    option_pattern = re.compile(r'^\s*[\[\(]?([A-Da-d])[\]\)\.]?\s*(.*)$')
    for part in parts[1:]:
        match = option_pattern.match(part.strip())
        if match:
            letter = match.group(1).upper()
            text = match.group(2)
            options.append((letter, text))


    if not options:
        return f"\\item {latex_escape(stem)}"

    formatted = f"\\item {latex_escape(stem)}\n"
    formatted += "\\begin{enumerate}[label=\\textbf{\\Alph*}, itemsep=0.5ex, leftmargin=*]\n"
    for letter, text in options:
        # Sanitize text for LaTeX
        formatted += f"    \\item {latex_escape(text)}\n"
    formatted += "\\end{enumerate}"

    return formatted


def get_strict_diagram_prompt(question_text: Optional[str], subject: Optional[str] = None, grade: Optional[str] = None) -> str:
    """Generate a strict prompt for diagram generation."""
    context = ""
    if subject:
        context += f"Subject: {subject}. "
    if grade:
        context += f"Grade: {grade}. "
    return (
        f"{context}Generate a clean, contextually accurate diagram or illustration relevant to the following question for a school exam paper. "
        "Do NOT include any text, labels, or explanations in the image, except for essential diagram indicators (such as A, B, 1, 2, etc.), mathematical symbols, or blank lines. Only draw the diagram or illustration itself.\nQuestion: " + (question_text or "")
    )


def process_question(q: str, q_idx: int = 1, include_images: bool = True, subject: Optional[str] = None, grade: Optional[str] = None) -> str:
    """Process individual question with proper LaTeX formatting, optionally including images for diagrams. Enhanced: always generate diagrams, clean table rendering, no placeholders."""
    try:
        logger.debug(f"Processing question: {q[:50]}...")
        metadata = extract_metadata(q)
        clean_q = metadata["clean_text"]
        marks = metadata["marks"]
        needs_diagram = metadata["needs_diagram"]
        needs_table = metadata["needs_table"]
        is_mcq = metadata["is_mcq"]
        table_data: Optional[str] = None
        # Extract table data if table is required
        if needs_table:
            clean_q, table_data = extract_table_data_from_question(clean_q)
        # MCQ formatting
        if is_mcq:
            formatted_q = format_mcq_question(clean_q)
        else:
            processed_q = latex_escape(clean_q)
            formatted_q = f"\\item {processed_q}"
        marks_text = f"\\hfill \\textbf{{({marks} marks)}}" if marks != "0" else ""
        formatted_q += marks_text + "\n"
        # Diagrams: always generate, retry up to 3 times
        if needs_diagram:
            if include_images:
                logger.info(f"[IMAGE] Image generation enabled for question {q_idx}: {clean_q[:50]}...")
                q_hash = hashlib.md5(clean_q.encode('utf-8')).hexdigest()[:10]
                image_filename = f"diagram_{q_hash}.png"
                image_path = os.path.join(UPLOAD_DIR, image_filename)
                latex_image_path = image_filename
                default_prompt = get_strict_diagram_prompt(clean_q, subject=subject, grade=grade)
                
                attempts = 0
                while not os.path.exists(image_path) and attempts < 3:
                    try:
                        logger.info(f"[GEN] Generating diagram for question {q_idx} (attempt {attempts + 1}/3)...")
                        result = generate_diagram_image(default_prompt, output_filename=image_path)
                        if result and os.path.exists(image_path):
                            logger.info(f"[OK] Diagram generated successfully for question {q_idx}: {image_filename}")
                            break
                        else:
                            logger.warning(f"[WARN] Diagram generation attempt {attempts + 1} failed for question {q_idx}")
                    except Exception as e:
                        logger.error(f"[ERROR] Diagram generation error for question {q_idx}: {e}")
                    attempts += 1
                    if not os.path.exists(image_path) and attempts < 3:
                        time.sleep(1.5 * attempts)  # Exponential backoff
                
                if not os.path.exists(image_path):
                    logger.error(f"[ERROR] Failed to generate diagram after 3 attempts for question {q_idx}: {clean_q[:50]}...")
                    raise RuntimeError(f"Failed to generate diagram for question: {clean_q}")
                
                # Use triple-quoted string for LaTeX block, no literal \n
                formatted_q += rf'''
\vspace{{0.5cm}}
\begin{{center}}
\includegraphics[width=0.7\linewidth]{{{latex_image_path}}}
\end{{center}}
\vspace{{0.5cm}}
'''.replace("\n", "\n")
            else:
                logger.info(f"[INFO] Question {q_idx} needs diagram but image generation is disabled")
        else:
            logger.debug(f"[DEBUG] Question {q_idx} does not require diagram")
        # Table: only one, after question text, never markdown
        if needs_table:
            # import generate_table_latex_from_question lazily to avoid circular import
            from qp_model import generate_table_latex_from_question
            table_code = generate_table_latex_from_question(clean_q, table_data=table_data or "")
            if not table_code or "\\begin{tabular}" not in table_code:
                logger.error(f"Failed to generate LaTeX table for question: {clean_q}")
                raise RuntimeError(f"Failed to generate LaTeX table for question: {clean_q}")
            # Use triple-quoted string for LaTeX block, no literal \n
            formatted_q += f"\n\\vspace{{0.5cm}}\n{table_code}\n\\vspace{{0.5cm}}\n"
        return formatted_q
    except Exception as e:
        logger.error(f"Error processing question: {e}\n{traceback.format_exc()}")
        raise


def format_questions(paper_text: str, include_images: bool = True, subject: Optional[str] = None, grade: Optional[str] = None) -> str:
    """Format all questions with proper numbering and spacing, optionally including images for diagrams."""
    logger.info("Formatting questions for LaTeX")
    questions = _parse_paper_text_to_questions(paper_text)
    formatted_questions = []
    
    for i, q in enumerate(questions, 1):
        try:
            formatted = process_question(q, q_idx=i, include_images=include_images, subject=subject, grade=grade)
            formatted_questions.append(formatted)
        except Exception as e:
            logger.error(f"Error formatting question {i}: {e}")
            raise ValueError(f"Question {i} could not be rendered; paper generation stopped.") from e
    
    return "\n".join(formatted_questions)


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
                if default_name.lower() == str(col).strip().lower():
                    column_map[key] = col
                    found = True
                    break
            if not found:
                # If a standard name isn't found, fallback to index
                if key == 'question': column_map[key] = df.columns[7] # H
                elif key == 'options': column_map[key] = df.columns[8] # I
                elif key == 'marks': column_map[key] = df.columns[6]   # G

        for index, row in df.iterrows():
            question_value = row.get(column_map['question'], '')
            question_text = str(question_value).strip() if pd.notna(question_value) else ''
            options_value = row.get(column_map['options'], '')
            options_text = str(options_value).strip() if pd.notna(options_value) else ''
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
