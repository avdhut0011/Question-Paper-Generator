"""Preview generation service moved from qp_model.py
Contains generate_html_preview with image generation preserved.
Do NOT modify logic; only relocated and fixed imports.
"""
import os
from html import escape
import re
import hashlib
from datetime import datetime
from typing import Optional

from config import UPLOAD_DIR, logger
from services.question_service import _parse_paper_text_to_questions, extract_metadata, get_strict_diagram_prompt
from imagen import generate_diagram_image
from PIL import Image


def generate_html_preview(grade: str, subject: str, total_marks: int, date_str: str, paper_text: str, include_images: bool = True) -> str:
    """Generate a professional HTML preview of the question paper, optionally including images for diagrams."""
    logger.info("Generating HTML preview")
    questions = _parse_paper_text_to_questions(paper_text)
    questions_html = []
    
    for i, q in enumerate(questions, 1):
        metadata = extract_metadata(q)
        clean_q = metadata["clean_text"]
        marks = metadata["marks"]
        needs_diagram = metadata["needs_diagram"]
        needs_table = metadata["needs_table"]
        is_mcq = metadata["is_mcq"]
        blooms_level = metadata["blooms_level"]
        # Distinct question number and marks badge
        marks_html = f'<span class="question-marks-badge">{marks} marks</span>' if marks != "0" else ""
        # For MCQ, show only the stem as question text
        if is_mcq:
            parts = clean_q.split('\n')
            question_text = escape(parts[0].strip())
        else:
            question_text = escape(clean_q)
        # Question header: number, text, marks
        question_header = f'<div class="question-header"><span class="question-number">{i}.</span> <span class="question-text-main">{question_text}</span> {marks_html}</div>'
        # MCQ options
        mcq_html = ""
        if is_mcq:
            options_html = '<div class="mcq-options">'
            option_pattern = re.compile(r'^\s*[\[\(]?([A-D])[\]\)\.]?\s*(.*)$')
            # Split the clean question text (which now contains all options) into lines
            parts = clean_q.split('\n')
            for part in parts[1:]: # Start from the second line for options
                match = option_pattern.match(part.strip())
                if match:
                    letter = match.group(1).upper()
                    text = escape(match.group(2).strip())
                    # Add each option to the HTML list
                    options_html += f'<div class="mcq-option"><span class="option-letter">{letter}</span> {text}</div>'
            options_html += '</div>'
            mcq_html = options_html
        # Diagram
        diagram_html = ""
        if needs_diagram:
            if include_images:
                logger.info(f"[IMAGE] Generating diagram for preview question {i}: {clean_q[:50]}...")
                q_hash = hashlib.md5(clean_q.encode('utf-8')).hexdigest()[:10]
                image_filename = f"diagram_{q_hash}.png"
                image_path = os.path.join(UPLOAD_DIR, image_filename)
                default_prompt = get_strict_diagram_prompt(clean_q, subject=subject, grade=grade)
                
                if not os.path.exists(image_path):
                    try:
                        logger.info(f"[GEN] Generating diagram for preview question {i}...")
                        result = generate_diagram_image(default_prompt, output_filename=image_path)
                        if result and os.path.exists(image_path):
                            # Verify integrity
                            try:
                                with Image.open(image_path) as im:
                                    im.verify()
                                logger.info(f"[OK] Diagram generated and verified for preview question {i}: {image_filename}")
                            except Exception as verr:
                                logger.warning(f"[WARN] Generated diagram failed integrity check: {verr}")
                                try:
                                    os.remove(image_path)
                                except Exception:
                                    pass
                        else:
                            logger.error(f"[ERROR] Diagram generation failed for preview question {i}")
                    except Exception as e:
                        logger.error(f"[ERROR] Diagram generation error for preview question {i}: {e}")
                else:
                    logger.info(f"[INFO] Diagram already exists for preview question {i}: {image_filename}")
                
                rel_path = f"{UPLOAD_DIR}/{image_filename}"
                diagram_html = f'<div class="diagram-image-card"><img src="/{rel_path}" alt="Diagram for question {i}" class="diagram-img"/>'
                diagram_html += '<div class="diagram-note">No text or labels should appear in the diagram except for essential indicators (A, B, 1, 2, etc.), mathematical symbols, or blank lines.</div></div>'
            else:
                logger.info(f"[INFO] Preview question {i} needs diagram but image generation is disabled")

        else:
            logger.debug(f"[DEBUG] Preview question {i} does not require diagram")
        # Table placeholder (if needed)
        table_html = ""
        if needs_table:
            table_html = """
            <div class="table-placeholder">
                <i class="fas fa-table"></i> Table: Content would appear here
            </div>
            """
        # Bloom's level
        blooms_html = f'<div class="blooms-level"><strong>Bloom\'s:</strong> {blooms_level}</div>' if blooms_level else ""
        # Compose question card
        question_html = f"""
        <div class="question-card">
            {question_header}
            {diagram_html}
            {mcq_html}
            {table_html}
            {blooms_html}
        </div>
        """
        questions_html.append(question_html)
    # MathJax config for mhchem and siunitx
    mathjax_config = '''<script type="text/x-mathjax-config">
    MathJax = {
      tex: {
        packages: {'[+]': ['mhchem', 'siunitx']},
        inlineMath: [['$', '$'], ['\\(', '\\)']],
        displayMath: [['$$', '$$'], ['\\[', '\\]']],
        processEscapes: true
      },
      options: {
        ignoreHtmlClass: 'tex2jax_ignore',
        processHtmlClass: 'tex2jax_process'
      },
      loader: {load: ['[tex]/mhchem', '[tex]/siunitx']}
    };
    </script>'''
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{grade} {subject} Question Paper Preview</title>
    <link href=\"https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Playfair+Display:wght@700&display=swap\" rel=\"stylesheet\">
    <link rel=\"stylesheet\" href=\"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css\">
    <script src=\"https://polyfill.io/v3/polyfill.min.js?features=es6\"></script>
    {mathjax_config}
    <script id=\"MathJax-script\" async src=\"https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js\"></script>
    <style>
        body {{
            font-family: 'Roboto', sans-serif;
            background: linear-gradient(120deg, #f5f7fa 0%, #e3e9f0 100%);
            min-height: 100vh;
            margin: 0;
        }}
        .container {{
            max-width: 900px;
            margin: 40px auto 0 auto;
            padding: 24px 18px 40px 18px;
            background-color: #fff;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(44,62,80,0.10);
        }}
        .header {{
            background: linear-gradient(135deg, #2c3e50, #3498db);
            color: white;
            padding: 30px 0 18px 0;
            margin-bottom: 32px;
            text-align: center;
            border-radius: 8px 8px 0 0;
            position: relative;
        }}
        .header h1 {{
            font-family: 'Playfair Display', serif;
            font-size: 2.3rem;
            margin-bottom: 6px;
        }}
        .header .subtitle {{
            font-size: 1.15rem;
            opacity: 0.93;
        }}
        .header .date {{
            font-size: 1rem;
            margin-top: 10px;
            opacity: 0.8;
        }}
        .instructions {{
            background-color: #f8f9fa;
            border-left: 4px solid #3498db;
            padding: 20px 24px;
            margin-bottom: 32px;
            border-radius: 4px;
        }}
        .instructions h2 {{
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 1.15rem;
        }}
        .instructions ul {{
            padding-left: 20px;
        }}
        .instructions li {{
            margin-bottom: 5px;
        }}
        .question-container {{
            margin-bottom: 40px;
        }}
        .question-container h2 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 5px;
            margin-bottom: 20px;
            font-size: 1.3rem;
        }}
        .question-card {{
            background: #fafdff;
            border: 1.5px solid #e3e9f0;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(44,62,80,0.06);
            margin-bottom: 28px;
            padding: 22px 20px 18px 20px;
            transition: box-shadow 0.2s, border 0.2s;
            position: relative;
        }}
        .question-card:hover {{
            box-shadow: 0 6px 24px rgba(44,62,80,0.13);
            border: 1.5px solid #b0b8c1;
        }}
        .question-header {{
            display: flex;
            align-items: center;
            margin-bottom: 12px;
        }}
        .question-number {{
            background: #3498db;
            color: #fff;
            border-radius: 50%;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 1.1rem;
            margin-right: 16px;
            box-shadow: 0 2px 6px rgba(44,62,80,0.10);
        }}
        .question-text-main {{
            font-size: 1.08rem;
            font-weight: 500;
            color: #2c3e50;
            flex: 1;
        }}
        .question-marks-badge {{
            background: #2c3e50;
            color: #fff;
            border-radius: 16px;
            padding: 4px 14px;
            font-size: 0.98rem;
            font-weight: 500;
            margin-left: 18px;
            box-shadow: 0 1px 4px rgba(44,62,80,0.08);
        }}
        .diagram-image-card {{
            margin: 18px 0 10px 0;
            padding: 14px 10px 10px 10px;
            background: #f8f9fa;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(44,62,80,0.07);
            text-align: center;
        }}
        .diagram-img {{
            max-width: 80%;
            height: auto;
            display: block;
            margin: 0 auto 10px auto;
            border-radius: 6px;
            border: 1.5px solid #b0b8c1;
            box-shadow: 0 1px 4px rgba(44,62,80,0.10);
        }}
        .diagram-note {{
            font-size: 0.95em;
            color: #6c757d;
            margin-top: 8px;
        }}
        .mcq-options {{
            margin: 15px 0 0 30px;
        }}
        .mcq-option {{
            margin-bottom: 8px;
            padding-left: 10px;
            border-left: 2px solid #dee2e6;
        }}
        .option-letter {{
            font-weight: bold;
            margin-right: 10px;
            color: #2c3e50;
        }}
        .blooms-level {{
            margin-top: 10px;
            font-size: 0.97rem;
            color: #6c757d;
            font-style: italic;
        }}
        .footer {{
            text-align: center;
            margin-top: 50px;
            padding: 20px;
            color: #6c757d;
            font-size: 0.97rem;
            border-top: 1px solid #dee2e6;
            }}
        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}
            .header h1 {{
                font-size: 1.5rem;
            }}
            .question-card {{
                padding: 14px 8px 12px 8px;
            }}
            .question-header {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .question-number {{
                margin-bottom: 6px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{subject}</h1>
            <div class="subtitle">Grade {grade} Question Paper</div>
            <div class="date">{date_str} â€¢ {total_marks} Marks</div>
        </div>
        <div class="instructions">
            <h2>General Instructions</h2>
            <ul>
                <li>All questions are compulsory</li>
                <li>Marks for each question are indicated against it</li>
                <li>Answers should be brief and to the point</li>
                <li>For numerical problems, show all calculations</li>
                <li>Draw diagrams neatly where required</li>
                <li>Multiple choice questions must be answered by selecting the correct option</li>
            </ul>
        </div>
        <div class="question-container">
            <h2>Questions</h2>
            {"".join(questions_html)}
        </div>
        <div class="footer">
            <p>Generated using Academic Question Paper Generator â€¢ Confidential until exam day</p>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
