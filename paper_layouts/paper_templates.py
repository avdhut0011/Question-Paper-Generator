from services.latex_service import LATEX_PACKAGES, LATEX_HEADER

def get_default_paper_template(grade: str, subject: str, total_marks: int, date_str: str, time_str: str) -> str:
    half_marks = str(int(total_marks * 0.5))
    calc_allowed = 'allowed' if str(grade).isdigit() and int(grade) > 8 else 'not allowed'
    template = r"""\documentclass[12pt]{article}
{LATEX_PACKAGES}
{LATEX_HEADER}

\begin{document}

\begin{center}
	extbf{ASHOKA GROUP OF SCHOOLS} \\
	extbf{ASHOKA UNIVERSAL SCHOOL} \\
	extbf{Academic Session 2025–2026} \\
	extbf{Assessment–I} \\
	extbf{Subject: <<SUBJECT>>} \\
	extbf{Grade: <<GRADE>>}
\end{center}
\vspace{1cm}

\begin{multicols}{2}
    \begin{flushleft}
        	extbf{Date:} <<DATE>>
    \end{flushleft}
    \begin{flushright}
        	extbf{Marks:} <<TOTAL>>\\
        	extbf{Time:} <<TIME>>
    \end{flushright}
\end{multicols}

\begin{tcolorbox}[colback=gray!5,colframe=black,title=\\textbf{General Instructions}]
\begin{itemize}[leftmargin=*, nosep]
    \item All questions are compulsory.
    \item Marks for each question are indicated against it.
    \item Answers should be brief and to the point.
    \item For numerical problems, show all calculations.
    \item Use of calculators is <<CALC_ALLOWED>>.
    \item Draw diagrams neatly where required.
    \item Multiple choice questions must be answered by selecting the correct option.
\end{itemize}
\end{tcolorbox}

\vspace{1cm}
\begin{enumerate}[leftmargin=*, itemsep=1.2cm, topsep=0.5cm]
<<QUESTIONS>>
\end{enumerate}

\vfill
\begin{center}
	extit{--- End of Question Paper ---}
\end{center}
\end{document}
"""
    return template.replace('<<SUBJECT>>', subject).replace('<<GRADE>>', grade).replace('<<DATE>>', date_str).replace('<<TIME>>', time_str).replace('<<TOTAL>>', str(total_marks)).replace('<<CALC_ALLOWED>>', calc_allowed).replace('{LATEX_PACKAGES}', LATEX_PACKAGES).replace('{LATEX_HEADER}', LATEX_HEADER).replace('<<HALF>>', half_marks)

def get_aus_paper_template(grade: str, subject: str, total_marks: int, date_str: str, time_str: str) -> str:
    """Return AUS exam paper template with proper formatting."""
    return rf"""\documentclass[12pt, a4paper]{{exam}}
% Essential packages for PDFLaTeX compatibility
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\usepackage{{textcomp}}
\usepackage{{gensymb}}
\usepackage{{amsmath}}
\usepackage{{amssymb}}
\usepackage{{amsfonts}}
\usepackage{{amsthm}}
\usepackage{{mathrsfs}}
\usepackage{{geometry}}
\usepackage{{graphicx}}
\usepackage{{tikz}}
\usepackage{{pgfplots}}
\pgfplotsset{{compat=1.15}}
\usepackage{{enumitem}}
\usepackage{{tabularx}}
\usepackage{{booktabs}}
\usepackage{{array}}
\usepackage{{float}}
\usepackage{{wrapfig}}
\usepackage{{multicol}}
\usepackage{{multirow}}
\usepackage{{longtable}}
\usepackage{{xcolor}}
\usepackage{{setspace}}
\usepackage{{titlesec}}
\usepackage{{lastpage}}
\usepackage{{fancyhdr}}
\usepackage{{caption}}
\usepackage{{subcaption}}
\usepackage{{tcolorbox}}
\usepackage[version=4]{{mhchem}}
\usepackage{{chemformula}}
\usepackage{{siunitx}}
\usepackage{{hyperref}}
\usetikzlibrary{{shadows,patterns,shapes.geometric,calc,positioning,arrows.meta}}

% PAGE GEOMETRY & SPACING
\geometry{{a4paper, margin=1.5cm, top=2cm, bottom=2cm, headheight=15pt}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.5em}}
\renewcommand{{\baselinestretch}}{{1.1}}

% CUSTOM COLORS
\definecolor{{ashokablue}}{{RGB}}{{0, 82, 155}}
\definecolor{{ashokagold}}{{RGB}}{{255, 204, 0}}
\definecolor{{lightblue}}{{RGB}}{{240, 248, 255}}

% HEADER & FOOTER
\pagestyle{{headandfoot}}
\firstpageheader{{}} {{}} {{\textbf{{Document No. ACA/R/08 Rev. 00 Date : 02.02.2022}}}}
\runningheader{{}} {{}} {{}}
\firstpagefooter{{2025-26/Assessment I/Grade {grade}/{subject}}} {{}} {{\textbf{{Page \thepage\ of \pageref{{LastPage}}}}}}
\runningfooter{{2025-26/Assessment I/Grade {grade}/{subject}}} {{}} {{\textbf{{Page \thepage\ of \pageref{{LastPage}}}}}}

% Section formatting
\titleformat{{\section}}{{\normalfont\Large\bfseries}}{{\thesection}}{{1em}}{{}}
\titlespacing{{\section}}{{0pt}}{{12pt}}{{6pt}}

% Question formatting
\renewcommand{{\questionshook}}{{\setlength{{\itemsep}}{{12pt}}}}
\renewcommand{{\partshook}}{{\setlength{{\itemsep}}{{8pt}}}}

\begin{{document}}

% LOGO & HEADER
\begin{{center}}
\textbf{{\textcolor{{ashokablue}}{{ASHOKA GROUP OF SCHOOLS}}}}\\
\vspace{{0.2cm}}
\textbf{{ACADEMIC SESSION 2025–2026}}\\
\vspace{{0.3cm}}
\textbf{{ASSESSMENT 1}}\\
\vspace{{0.3cm}}
\textbf{{GRADE {grade.upper()}}}\\
\vspace{{0.3cm}}
\textbf{{Maximum Marks: {total_marks} \hfill {subject.upper()} \hfill \hspace{{1cm}} Time: 2 Hours }}\\
\vspace{{0.5cm}}

% Instructions box
\tikzstyle{{mybox}} = [draw=ashokablue, fill=lightblue, very thick, rectangle, rounded corners, inner sep=10pt, inner ysep=10pt]
\begin{{tikzpicture}}
\node [mybox] {{
\begin{{minipage}}{{0.95\textwidth}}
\begin{{center}}
\textbf{{\color{{ashokablue}}INSTRUCTIONS}}
\end{{center}}
\begin{{itemize}}[leftmargin=*]
\item Answer to this paper must be written on the paper provided separately.
\item You will not be allowed to write during the first 15 minutes. This time is to be spent in reading the question paper.
\item The time given at the head of this paper is the time allowed for writing the answers.
\item Attempt all questions from \textbf{{Section I}} and any \textbf{{four}} questions from \textbf{{Section II}}.
\item The intended marks for questions or parts of questions are given in brackets [ ].
\item All working, including rough work, should be done on the same sheet as the rest of the answer.
\item Draw neat diagrams wherever necessary.
\end{{itemize}}
\end{{minipage}}
}};
\end{{tikzpicture}}
\end{{center}}

\begin{{center}}
\textbf{{\color{{black}} SECTION I ({int(total_marks * 0.5)} Marks) \\ (Attempt all questions)}}
\end{{center}}

\begin{{questions}}
<<QUESTIONS>>
\end{{questions}}

\begin{{center}}
\textbf{{\Large }}
\end{{center}}

\end{{document}}
"""

def get_aga_paper_template(grade: str, subject: str, total_marks: int, date_str: str, time_str: str) -> str:
    """Return AGA exam paper template with proper formatting."""
    return rf"""\documentclass[11pt]{{exam}}
% Essential packages for PDFLaTeX compatibility
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\usepackage{{textcomp}}
\usepackage{{gensymb}}
\usepackage{{amsmath}}
\usepackage{{amssymb}}
\usepackage{{amsfonts}}
\usepackage{{amsthm}}
\usepackage{{mathrsfs}}
\usepackage{{geometry}}
\usepackage{{graphicx}}
\usepackage{{tikz}}
\usepackage{{pgfplots}}
\pgfplotsset{{compat=1.15}}
\usepackage{{enumitem}}
\usepackage{{lastpage}}
\usepackage{{fancyhdr}}
\usepackage{{booktabs}}
\usepackage{{array}}
\usepackage{{tabularx}}
\usepackage{{multirow}}
\usepackage{{multicol}}
\usepackage{{longtable}}
\usepackage{{float}}
\usepackage{{wrapfig}}
\usepackage{{caption}}
\usepackage{{subcaption}}
\usepackage{{xcolor}}
\usepackage{{setspace}}
\usepackage{{tcolorbox}}
\usepackage[version=4]{{mhchem}}
\usepackage{{chemformula}}
\usepackage{{siunitx}}
\usepackage{{hyperref}}
\usetikzlibrary{{shapes, shadows, arrows.meta, positioning, patterns, angles, quotes, calc}}

\geometry{{a4paper, margin=1in}}

% HEADER & FOOTER
\pagestyle{{fancy}}
\fancyhf{{}} % Clear all header and footer fields
\fancyhead[R]{{\textsc{{AGA Term1//2025-2026/Grade-{grade}/{subject}/Paper1}}}}
\fancyfoot[C]{{Page \thepage\ of \pageref{{LastPage}}}}
\fancyfoot[R]{{\textsc{{Page Total - {total_marks}}}}}
\renewcommand{{\headrulewidth}}{{1pt}}
\renewcommand{{\footrulewidth}}{{1pt}}

\pointpoints{{mark}}{{marks}}
\boxedpoints
\pointsdroppedatright
\marginpointname{{ \\points}}

\begin{{document}}

\begin{{center}}
\textbf{{\\Large AGA EXAMINATION}}\\\\
\vspace{{0.3cm}}
\textbf{{Grade {grade} - {subject}}}\\\\
\vspace{{0.2cm}}
\textbf{{Date: {date_str} \\hfill Time: {time_str}}}\\\\
\vspace{{0.2cm}}
\textbf{{Total Marks: {total_marks}}}\\\\
\vspace{{0.5cm}}
\end{{center}}

\begin{{tcolorbox}}[colback=gray!10,colframe=black,title=\\textbf{{Instructions}}]
\begin{{itemize}}[leftmargin=*, nosep]
\item Read all questions carefully before answering.
\item Answer all questions in the spaces provided.
\item Show all working for numerical problems.
\item Use appropriate units where required.
\item Marks are indicated in brackets for each question.
\end{{itemize}}
\end{{tcolorbox}}

\vspace{{1cm}}

\begin{{questions}}
<<QUESTIONS>>
\end{{questions}}

\newpage
\begin{{center}}
\textbf{{BLANK PAGE}}
\end{{center}}

\end{{document}}
"""
