import html
import os
import re
import shutil
import subprocess
from pathlib import Path

SAFE_MATH_COMMANDS = set('frac sqrt times div cdot pm mp le leq ge geq neq approx pi theta alpha beta gamma delta Delta sigma sum int infinity infty sin cos tan log ln exp left right text mathrm mathbf overline vec hat angle degree circ perp parallel overrightarrow binom begin end matrix pmatrix bmatrix cases quad qquad'.split())


def escape_plain(value):
    replacements = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
                    '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(replacements.get(c, c) for c in str(value))


def latex_text(value):
    """Preserve explicitly delimited math while rejecting executable TeX commands."""
    parts = re.split(r'(\$[^$\n]+\$)', str(value))
    rendered = []
    for part in parts:
        if part.startswith('$') and part.endswith('$') and len(part) > 2:
            commands = re.findall(r'\\([A-Za-z]+)', part)
            if set(commands) - SAFE_MATH_COMMANDS or any(x in part for x in ('^^', '%', '#')):
                raise ValueError('Unsupported LaTeX in a mathematical expression. Use ordinary mathematical notation.')
            # Environments are not accepted inside inline math.
            if '\\begin' in part or '\\end' in part:
                raise ValueError('Math environments are not supported inside inline expressions.')
            rendered.append(part)
        else:
            rendered.append(escape_plain(part))
    return ''.join(rendered)


def render_latex(snapshot, school_name):
    b = snapshot['blueprint']
    questions = []
    for q in snapshot['questions']:
        entry = f"\\item {latex_text(q['stem'])} \\hfill \\textbf{{[{q['marks']}]}}"
        if q['options']:
            entry += '\n\\begin{enumerate}[label=\\Alph*.]\n'
            entry += '\n'.join('\\item ' + latex_text(option) for option in q['options'])
            entry += '\n\\end{enumerate}'
        questions.append(entry)
    return r'''\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,enumitem,geometry}
\geometry{margin=22mm}
\begin{document}
\begin{center}
\textbf{ASHOKA GROUP OF SCHOOLS}\\
\textbf{<<SCHOOL>>}\\
\textbf{<<TITLE>>}\\
Academic year: <<YEAR>>\\
Grade: <<GRADE>> \quad Subject: <<SUBJECT>> \quad Board: <<BOARD>>\\
Time: <<DURATION>> minutes \quad Maximum marks: <<MARKS>>
\end{center}
All questions are compulsory. Marks are shown in brackets.
\begin{enumerate}[itemsep=1.3em]
<<QUESTIONS>>
\end{enumerate}
\end{document}
'''.replace('<<SCHOOL>>', escape_plain(school_name)).replace('<<TITLE>>', escape_plain(b['title'])) \
        .replace('<<YEAR>>', escape_plain(b['academic_year'])).replace('<<GRADE>>', escape_plain(b['grade'])) \
        .replace('<<SUBJECT>>', escape_plain(b['subject'])).replace('<<BOARD>>', escape_plain(b['board'])) \
        .replace('<<DURATION>>', str(b['duration_minutes'])).replace('<<MARKS>>', str(b['total_marks'])) \
        .replace('<<QUESTIONS>>', '\n'.join(questions))


def compile_pdf(tex_path):
    compiler = shutil.which('pdflatex')
    if not compiler:
        raise ValueError('PDFLaTeX is not installed on the worker. Install a TeX distribution or set QPG_REQUIRE_PDF=false for HTML/LaTeX-only output.')
    path = Path(tex_path).resolve()
    env = dict(os.environ, openin_any='p', openout_any='p')
    try:
        result = subprocess.run([compiler, '-no-shell-escape', '-interaction=nonstopmode',
                                 '-halt-on-error', path.name], cwd=path.parent, env=env,
                                capture_output=True, text=True, errors='replace', timeout=90)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PDF rendering timed out; the paper was not completed.') from exc
    pdf = path.with_suffix('.pdf')
    if result.returncode or not pdf.is_file() or not pdf.stat().st_size:
        raise ValueError('PDF rendering failed. Review the LaTeX and worker log; content was not silently simplified.')
    return pdf
