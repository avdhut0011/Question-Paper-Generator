"""LaTeX-related utilities and compilation helpers.
Relocated from qp_model.py without logic changes.
"""
import os
import re
import subprocess
import traceback
import time
import shutil
from typing import Tuple

from config import logger

# Enhanced LaTeX template configuration - Foolproof version
LATEX_PACKAGES = r"""
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage[a4paper, margin=1in]{geometry}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{array}
\usepackage{tabularx}
\usepackage{multirow}
\usepackage{float}
\usepackage{longtable}
\usepackage{hyperref}
\usepackage{lmodern}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{textcomp}
\usepackage{gensymb}
\usepackage{caption}
\usepackage{wrapfig}
\usepackage{setspace}
\usepackage{multicol}
\usepackage{tcolorbox}

% Custom commands for compatibility
\newcommand{\si}[1]{\text{#1}}
\newcommand{\SI}[2]{#1\text{ #2}}
\newcommand{\num}[1]{#1}
\newcommand{\ang}[1]{#1\textdegree}
\newcommand{\degree}{\textdegree}
\newcommand{\celsius}{\textdegree C}
\newcommand{\fahrenheit}{\textdegree F}
\newcommand{\kelvin}{K}
\newcommand{\ohm}{\Omega}
\newcommand{\micro}{\mu}
\newcommand{\per}{/}
\newcommand{\squared}{^2}
\newcommand{\cubed}{^3}
\newcommand{\tothe}{^}
\newcommand{\raiseto}{^}
\newcommand{\raisetothe}{^}
"""

LATEX_HEADER = r"""
\setlength{\parindent}{0pt}
\setlength{\headheight}{15pt}
\addtolength{\topmargin}{-3pt}

% Header and Footer
\pagestyle{fancy}
\fancyhf{}
\rhead{\textsc{Assessment}}
\lhead{\textsc{Academic Session}}
\cfoot{Page \thepage\ of \pageref{LastPage}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0.4pt}

% Custom symbols
\newcommand{\rupee}{\textdollar}
\newcommand{\degreeC}{\degree C}

% Diagram placeholder
\newcommand{\diagramplaceholder}[1]{%
\begin{center}
\fbox{\parbox{0.8\linewidth}{\centering\textbf{Diagram:} #1\\[2cm]}}
\end{center}
}

% Table placeholder
\newcommand{\tableplaceholder}[1]{%
\begin{center}
\begin{tabular}{|c|c|c|}
\hline
\multicolumn{3}{|c|}{\textbf{Table: #1}} \\
\hline
Column 1 & Column 2 & Column 3 \\
\hline
Data 1 & Data 2 & Data 3 \\
\hline
Data 4 & Data 5 & Data 6 \\
\hline
\end{tabular}
\end{center}
}
"""


def compile_latex_to_pdf(tex_path: str, pdf_path: str) -> Tuple[bool, str | None]:
    """Compile without destructive content fallbacks or executable TeX commands."""
    from school_platform.rendering import compile_pdf
    try:
        compiled = compile_pdf(tex_path)
        if os.path.abspath(compiled) != os.path.abspath(pdf_path):
            shutil.copyfile(compiled, pdf_path)
        return True, None
    except (ValueError, OSError) as exc:
        return False, str(exc)


def _compile_latex_fallback(tex_path: str, pdf_path: str) -> Tuple[bool, str | None]:
    """Fallback LaTeX compilation with basic error handling."""
    logger.info(f"Using fallback LaTeX compilation: {tex_path}")
    error_log = None
    max_attempts = 3
    success = False
    try:
        with open(tex_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Fix common LaTeX issues
        content = re.sub(r'\\si\{([^}]*)\}', r'\\text{\1}', content)
        content = re.sub(r'\\SI\{([^}]*)\}\{([^}]*)\}', r'\1\\text{ \2}', content)
        content = re.sub(r'\$\s*\$', '', content)  # Remove empty math
        content = re.sub(r'(?<!\\)&', r'\\&', content)  # Escape unescaped &
        content = re.sub(r'(?<!\\)%', r'\\%', content)  # Escape unescaped %
        content = re.sub(r'(?<!\\)#', r'\\#', content)  # Escape unescaped #
        content = re.sub(r'(?<!\\)\$', r'\\$', content)  # Escape unescaped $
        content = re.sub(r'(?<!\\)_', r'\\_', content)  # Escape unescaped _
        content = re.sub(r'(?<!\\)\^', r'\\textasciicircum', content)  # Escape unescaped ^

        # Fix broken LaTeX commands
        content = re.sub(r'\\begin\{([^}]+)\}([^\\]*?)\\end\{([^}]+)\}', 
                        lambda m: f'\\begin{{{m.group(1)}}}{m.group(2)}\\end{{{m.group(1)}}}' 
                        if m.group(1) == m.group(3) else m.group(0), content)

        # Remove problematic packages if they exist
        content = re.sub(r'\\usepackage\{siunitx\}', '', content)
        content = re.sub(r'\\usepackage\{chemformula\}', '', content)
        content = re.sub(r'\\usepackage\{mhchem\}', '', content)
        content = re.sub(r'\\usepackage\[.*?\]\{mhchem\}', '', content)

        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as fix_error:
        logger.warning(f"Could not apply basic fixes: {fix_error}")

    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", 
                 "-output-directory", os.path.dirname(tex_path), tex_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                text=True
            )

            if os.path.exists(pdf_path):
                logger.info("PDF generated successfully")
                success = True
                break
            else:
                error_log = f"Attempt {attempt}: PDF not generated"
                logger.warning(error_log)
        except subprocess.TimeoutExpired:
            error_log = f"Attempt {attempt}: Compilation timed out"
            logger.warning(error_log)
        except subprocess.CalledProcessError as e:
            error_log = f"Attempt {attempt}: LaTeX error\n{e.stderr}\n{e.stdout}"
            logger.error(error_log)
        except Exception as e:
            error_log = f"Attempt {attempt}: Unexpected error: {str(e)}"
            logger.error(error_log)

    # Clean up auxiliary files
    base_path = os.path.splitext(pdf_path)[0]
    for ext in ['.aux', '.log', '.out', '.toc', '.lof', '.lot']:
        aux_file = f"{base_path}{ext}"
        if os.path.exists(aux_file):
            try:
                os.remove(aux_file)
            except Exception:
                pass

    return success, error_log


def _compile_latex_minimal(tex_path: str, pdf_path: str) -> Tuple[bool, str | None]:
    """Compile LaTeX with minimal template for maximum compatibility."""
    try:
        logger.info("Trying minimal LaTeX template compilation...")
        with open(tex_path, 'r', encoding='utf-8') as f:
            content = f.read()
        doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', content, re.DOTALL)
        if not doc_match:
            return False, "Could not extract document content"
        body_content = doc_match.group(1)
        minimal_template = r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[a4paper, margin=1in]{geometry}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{multicol}
\usepackage{tcolorbox}
\usepackage{tikz}
\usetikzlibrary{calc, shapes.geometric, arrows, positioning}

% Custom commands for compatibility
\newcommand{\si}[1]{\text{#1}}
\newcommand{\SI}[2]{#1\text{ #2}}
\newcommand{\num}[1]{#1}
\newcommand{\ang}[1]{#1°}
\newcommand{\degree}{°}
\newcommand{\celsius}{°C}
\newcommand{\fahrenheit}{°F}
\newcommand{\kelvin}{K}
\newcommand{\ohm}{Ω}
\newcommand{\micro}{μ}
\newcommand{\per}{/}

\begin{document}
"""
        minimal_content = minimal_template + body_content + r"\end{document}"
        minimal_tex_path = tex_path.replace('.tex', '_minimal.tex')
        with open(minimal_tex_path, 'w', encoding='utf-8') as f:
            f.write(minimal_content)
        result = subprocess.run([
            'pdflatex', '-interaction=nonstopmode', '-halt-on-error',
            '-output-directory', os.path.dirname(minimal_tex_path), minimal_tex_path
        ], capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            minimal_pdf = minimal_tex_path.replace('.tex', '.pdf')
            if os.path.exists(minimal_pdf):
                shutil.copy2(minimal_pdf, pdf_path)
                os.remove(minimal_tex_path)
                os.remove(minimal_pdf)
                logger.info("Minimal LaTeX compilation successful")
                return True, None
        if os.path.exists(minimal_tex_path):
            os.remove(minimal_tex_path)
        return False, "Minimal compilation failed"
    except Exception as e:
        logger.error(f"Error in minimal LaTeX compilation: {e}")
        return False, str(e)


def _compile_latex_basic(tex_path: str, pdf_path: str) -> Tuple[bool, str | None]:
    """Compile LaTeX with basic template as last resort."""
    try:
        logger.info("Trying basic LaTeX template compilation...")
        with open(tex_path, 'r', encoding='utf-8') as f:
            content = f.read()
        enum_match = re.search(r'\\begin\{enumerate\}(.*?)\\end\{enumerate\}', content, re.DOTALL)
        if enum_match:
            questions_content = enum_match.group(1)
        else:
            doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', content, re.DOTALL)
            if doc_match:
                questions_content = doc_match.group(1)
            else:
                questions_content = "No questions found"
        questions_content = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', questions_content)
        questions_content = re.sub(r'\\[a-zA-Z]+', '', questions_content)
        questions_content = re.sub(r'\{[^}]*\}', '', questions_content)
        questions_content = re.sub(r'[\\$%#&_^]', '', questions_content)
        basic_template = f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath}}
\\usepackage{{geometry}}
\\geometry{{a4paper, margin=1in}}

\\begin{{document}}

\\begin{{center}}
\\textbf{{Question Paper}}
\\end{{center}}

\\begin{{enumerate}}
{questions_content}
\\end{{enumerate}}

\\end{{document}}
"""
        basic_tex_path = tex_path.replace('.tex', '_basic.tex')
        with open(basic_tex_path, 'w', encoding='utf-8') as f:
            f.write(basic_template)
        result = subprocess.run([
            'pdflatex', '-interaction=nonstopmode',
            '-output-directory', os.path.dirname(basic_tex_path), basic_tex_path
        ], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            basic_pdf = basic_tex_path.replace('.tex', '.pdf')
            if os.path.exists(basic_pdf):
                shutil.copy2(basic_pdf, pdf_path)
                os.remove(basic_tex_path)
                os.remove(basic_pdf)
                logger.info("Basic LaTeX compilation successful")
                return True, None
        if os.path.exists(basic_tex_path):
            os.remove(basic_tex_path)
        return False, "Basic compilation failed"
    except Exception as e:
        logger.error(f"Error in basic LaTeX compilation: {e}")
        return False, str(e)


def fix_invalid_siunitx_units(latex: str) -> str:
    r"""Replace invalid SIunitx units (e.g., \meter) with valid abbreviations (e.g., m) in LaTeX code."""
    unit_map = {
        r'\\meter': 'm',
        r'\\centimeter': 'cm',
        r'\\millimeter': 'mm',
        r'\\kilometer': 'km',
        r'\\gram': 'g',
        r'\\kilogram': 'kg',
        r'\\second': 's',
        r'\\minute': 'min',
        r'\\hour': 'h',
        r'\\ampere': 'A',
        r'\\kelvin': 'K',
        r'\\mole': 'mol',
        r'\\candela': 'cd',
        r'\\liter': 'L',
        r'\\litre': 'L',
        r'\\newton': 'N',
        r'\\joule': 'J',
        r'\\watt': 'W',
        r'\\pascal': 'Pa',
        r'\\coulomb': 'C',
        r'\\volt': 'V',
        r'\\siemens': 'S',
        r'\\weber': 'Wb',
        r'\\tesla': 'T',
        r'\\henry': 'H',
        r'\\lumen': 'lm',
        r'\\lux': 'lx',
        r'\\becquerel': 'Bq',
        r'\\gray': 'Gy',
        r'\\sievert': 'Sv',
        r'\\katal': 'kat',
    }
    for bad, good in unit_map.items():
        if re.search(bad, latex):
            logger.warning(f"Replacing invalid SIunitx unit {bad} with {good} in LaTeX output.")
            latex = re.sub(bad, lambda m: good, latex)
    math_fixes = {
        r'\\times': '×',
        r'\\div': '÷',
        r'\\cdot': '·',
        r'\\pm': '±',
        r'\\mp': '∓',
        r'\\leq': '≤',
        r'\\geq': '≥',
        r'\\neq': '≠',
        r'\\approx': '≈',
        r'\\equiv': '≡',
        r'\\sim': '∼',
        r'\\simeq': '≃',
        r'\\cong': '≅',
        r'\\propto': '∝',
        r'\\ll': '≪',
        r'\\gg': '≫',
        r'\\infty': '∞',
        r'\\partial': '∂',
        r'\\nabla': '∇',
        r'\\forall': '∀',
        r'\\exists': '∃',
        r'\\nexists': '∄',
        r'\\in': '∈',
        r'\\notin': '∉',
        r'\\ni': '∋',
        r'\\subset': '⊂',
        r'\\supset': '⊃',
        r'\\subseteq': '⊆',
        r'\\supseteq': '⊇',
        r'\\cup': '∪',
        r'\\cap': '∩',
        r'\\emptyset': '∅',
        r'\\varnothing': '∅',
    }
    for pattern, replacement in math_fixes.items():
        latex = re.sub(pattern, replacement, latex)
    return latex


def fix_split_latex_commands(latex: str) -> str:
    r"""Fixes split LaTeX commands like \c e{...} -> \ce{...}, \s i{...} -> \si{...}, etc."""
    patterns = [
        (r'\\c\s+e\s*{', r'\\ce{'),
        (r'\\s\\s+\+i\s*{', r'\\si{'),
        (r'\\S\s+I\s*{', r'\\SI{'),
        (r'\\f\s+r\s+a\s+c\s+t\s+i\s+o\s+n\s*{', r'\\fraction{'),
        (r'\\b\s+e\s+g\s+i\s+n\s*{', r'\\begin{'),
        (r'\\e\s+n\s+d\s*{', r'\\end{'),
    ]
    for pat, repl in patterns:
        if re.search(pat, latex):
            logger.warning(f"Fixing split LaTeX command: {pat} -> {repl}")
            latex = re.sub(pat, repl, latex)
    return latex


def fix_split_siunitx_macros(latex: str) -> str:
    r"""Replace split SIunitx macros like \centi\m with cm, \milli\m with mm, etc."""
    si_prefixes = [
        ('centi', 'c'),
        ('milli', 'm'),
        ('kilo', 'k'),
        ('micro', 'u'),
        ('nano', 'n'),
        ('deci', 'd'),
        ('deka', 'da'),
        ('mega', 'M'),
        ('giga', 'G'),
        ('tera', 'T'),
        ('pico', 'p'),
        ('femto', 'f'),
        ('atto', 'a'),
        ('zepto', 'z'),
        ('yocto', 'y'),
    ]
    si_units = [
        ('m', 'm'),
        ('g', 'g'),
        ('s', 's'),
        ('A', 'A'),
        ('K', 'K'),
        ('mol', 'mol'),
        ('cd', 'cd'),
        ('L', 'L'),
        ('N', 'N'),
        ('J', 'J'),
        ('W', 'W'),
        ('Pa', 'Pa'),
        ('C', 'C'),
        ('V', 'V'),
        ('F', 'F'),
        ('ohm', '\\Omega'),
        ('S', 'S'),
        ('Wb', 'Wb'),
        ('T', 'T'),
        ('H', 'H'),
        ('lm', 'lm'),
        ('lx', 'lx'),
        ('Bq', 'Bq'),
        ('Gy', 'Gy'),
        ('Sv', 'Sv'),
        ('kat', 'kat'),
    ]
    for prefix, p_abbr in si_prefixes:
        for unit, u_abbr in si_units:
            pattern = rf'\\{prefix}\s*\\{unit}'
            replacement = p_abbr + u_abbr
            if re.search(pattern, latex):
                logger.warning(f"Replacing split SIunitx macro {pattern} with {replacement} in LaTeX output.")
                latex = re.sub(pattern, replacement, latex)
    return latex


def fix_siunitx_braces(latex: str) -> str:
    r"""Replace \SI{...}{\cm} with \SI{...}{cm} and \si{\cm} with \si{cm}."""
    latex = re.sub(r'(\\SI\s*{[^}]+}{)\\([a-zA-Z]+)}', r'\1\2}', latex)
    latex = re.sub(r'(\\si\s*{)\\([a-zA-Z]+)}', r'\1\2}', latex)
    return latex


# Whitelist of allowed LaTeX macros (add more as needed)
ALLOWED_LATEX_MACROS = set([
    'SI', 'si', 'ce', 'frac', 'sqrt', 'textbf', 'textit', 'underline', 'begin', 'end',
    'includegraphics', 'vspace', 'hspace', 'caption', 'label', 'toprule', 'midrule', 'bottomrule',
])


def sanitize_latex_macros(latex: str) -> str:
    """Comment out or remove any LaTeX macro not in the whitelist."""
    def macro_replacer(match):
        macro = match.group(1)
        if macro in ALLOWED_LATEX_MACROS:
            return '\\' + macro
        else:
            logger.warning(f"Commenting out unknown LaTeX macro: \\{macro}")
            return f'%\\{macro}'
    return re.sub(r'\\([a-zA-Z]+)(?![a-zA-Z])', macro_replacer, latex)


def escape_latex_special_chars(latex: str) -> str:
    """Escape _, &, %, #, etc. outside math mode."""
    def replacer(match):
        text = match.group(0)
        text = text.replace('&', '\\&')
        text = text.replace('%', '\\%')
        text = text.replace('#', '\\#')
        text = text.replace('_', '\\_')
        return text
    return re.sub(r'([^$]+)', replacer, latex)


def remove_double_backslashes_in_text(latex: str) -> str:
    """Remove double backslashes in text (not in tables or math)."""
    return re.sub(r'\\\\(?!hline|begin|end|[a-zA-Z])', '', latex)


def clean_siunitx_units(latex: str) -> str:
    r"""
    Clean SIunitx units in \SI and \si macros.
    """
    unit_map = {
        r'\\ohm': r'\\Omega',
        r'\\newton': 'N',
        r'\\meter': 'm',
        r'\\centimeter': 'cm',
        r'\\millimeter': 'mm',
        r'\\kilometer': 'km',
        r'\\gram': 'g',
        r'\\kilogram': 'kg',
        r'\\second': 's',
        r'\\minute': 'min',
        r'\\hour': 'h',
        r'\\ampere': 'A',
        r'\\kelvin': 'K',
        r'\\mole': 'mol',
        r'\\candela': 'cd',
        r'\\liter': 'L',
        r'\\litre': 'L',
        r'\\joule': 'J',
        r'\\watt': 'W',
        r'\\pascal': 'Pa',
        r'\\coulomb': 'C',
        r'\\volt': 'V',
        r'\\siemens': 'S',
        r'\\weber': 'Wb',
        r'\\tesla': 'T',
        r'\\henry': 'H',
        r'\\lumen': 'lm',
        r'\\lux': 'lx',
        r'\\becquerel': 'Bq',
        r'\\gray': 'Gy',
        r'\\sievert': 'Sv',
        r'\\katal': 'kat',
    }
    def si_replacer(match):
        value = match.group(1)
        unit = match.group(2)
        for bad, good in unit_map.items():
            unit = re.sub(bad, good, unit)
        return f'\\SI{{{value}}}{{{unit}}}'
    latex = re.sub(r'\\SI\s*{([^}]+)}{([^}]+)}', si_replacer, latex)
    def si_only_replacer(match):
        unit = match.group(1)
        for bad, good in unit_map.items():
            unit = re.sub(bad, good, unit)
        return f'\\si{{{unit}}}'
    latex = re.sub(r'\\si\s*{([^}]+)}', si_only_replacer, latex)
    return latex


def enhanced_latex_processing(latex: str) -> str:
    """Enhanced LaTeX processing for foolproof compilation."""
    try:
        logger.info("Starting enhanced LaTeX processing...")
        latex = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1)/(\2)', latex)
        latex = re.sub(r'\\sqrt\{([^}]*)\}', r'√(\1)', latex)
        latex = re.sub(r'\\sqrt\[([^\]]*)\]\{([^}]*)\}', r'\1√(\2)', latex)
        latex = re.sub(r'\^\{([^}]*)\}', r'^(\1)', latex)
        latex = re.sub(r'\_\{([^}]*)\}', r'_(\1)', latex)
        math_symbols = {
            r'\\alpha': 'α', r'\\beta': 'β', r'\\gamma': 'γ', r'\\delta': 'δ',
            r'\\epsilon': 'ε', r'\\zeta': 'ζ', r'\\eta': 'η', r'\\theta': 'θ',
            r'\\lambda': 'λ', r'\\mu': 'μ', r'\\nu': 'ν', r'\\xi': 'ξ',
            r'\\pi': 'π', r'\\rho': 'ρ', r'\\sigma': 'σ', r'\\tau': 'τ',
            r'\\phi': 'φ', r'\\chi': 'χ', r'\\psi': 'ψ', r'\\omega': 'ω',
            r'\\Gamma': 'Γ', r'\\Delta': 'Δ', r'\\Theta': 'Θ', r'\\Lambda': 'Λ',
            r'\\Xi': 'Ξ', r'\\Pi': 'Π', r'\\Sigma': 'Σ', r'\\Upsilon': 'Υ',
            r'\\Phi': 'Φ', r'\\Psi': 'Ψ', r'\\Omega': 'Ω',
        }
        for pattern, replacement in math_symbols.items():
            latex = re.sub(pattern, replacement, latex)
        latex = re.sub(r'\\begin\{tabular\}\{[^}]*\}', lambda m: m.group(0).replace('|', ''), latex)
        latex = re.sub(r'\\item\s*\\item', r'\\item', latex)
        latex = re.sub(r'\$\s*\$', '', latex)
        latex = re.sub(r'\$([^$]*)\$\$([^$]*)\$', r'$\1\2$', latex)
        latex = re.sub(r'([^\\])\$', r'\1 $', latex)
        latex = re.sub(r'\$([^\\])', r'$ \1', latex)
        latex = re.sub(r'\\diagramplaceholder\{[^}]*\}', '', latex)
        latex = re.sub(r'\\tableplaceholder\{[^}]*\}', '', latex)
        latex = re.sub(r'\\\\+', r'\\\\', latex)
        logger.info("Enhanced LaTeX processing completed successfully")
        return latex
    except Exception as e:
        logger.error(f"Error in enhanced LaTeX processing: {e}")
        return latex


def generate_table_latex_from_question(question_text: str, table_data: str = "") -> str:
    """
    Generate a LaTeX tabular environment from table_data.
    Accepts either markdown-style tables or whitespace-separated values.
    """
    lines = [line.strip() for line in table_data.split('\n') if line.strip()]
    if not lines:
        return r"""
\begin{center}
\begin{tabular}{|c|c|c|}
\hline
Column 1 & Column 2 & Column 3 \\
\hline
Data 1 & Data 2 & Data 3 \\
\hline
\end{tabular}
\end{center}
"""
    if len(lines) > 1 and re.match(r'^\s*\|?\s*-+\s*\|', lines[1]):
        lines.pop(1)
    rows = []
    for line in lines:
        if "|" in line:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
        else:
            cells = [cell.strip() for cell in line.split()]
        rows.append(cells)
    ncols = max(len(row) for row in rows)
    latex = [r"\begin{center}", rf"\begin{{tabular}}{{|{'c|'*ncols}}}", r"\hline"]
    for row in rows:
        from school_platform.rendering import latex_text
        latex.append(" & ".join(latex_text(cell) for cell in row + [""] * (ncols - len(row))) + r" \\ \hline")
    latex.append(r"\end{tabular}")
    latex.append(r"\end{center}")
    return "\n".join(latex)
