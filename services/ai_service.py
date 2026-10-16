"""AI service module extracted from qp_model.py
Contains functions that call Gemini / select questions via AI.
Do not modify logic; only moved and fixed imports.
"""
from typing import Optional, List
import traceback
import random

from config import client, GENAI_AVAILABLE, GEMINI_MODEL, logger, types, genai


def generate_questions_for_paper(grade: str, subject: str, total_marks: int, difficulty_split: dict, num_questions: int, board: str, blooms_levels: list, custom_instructions: str, syllabus_text: Optional[str] = None, sample_text: Optional[str] = None) -> str:
    """Generate questions using Gemini API with custom instructions.
    Logic moved from qp_model.py without modification.
    """
    logger.info(f"Generating questions for Grade {grade} {subject} ({board})")
    blooms_str = ", ".join(blooms_levels)
    prompt = rf"""
Generate exactly {num_questions} {board}-style questions for Grade {grade} {subject}, totaling {total_marks} marks.
Use Bloom's taxonomy levels: {blooms_str}.

Key Requirements:
1. Difficulty Distribution:
   - Easy: {difficulty_split['easy']}% (Recall, Understand)
   - Medium: {difficulty_split['medium']}% (Apply, Analyze)
   - Hard: {difficulty_split['hard']}% (Evaluate, Create, Synthesize)

2. Question Types:
   - Short answer
   - Long answer
   - Very long answer (if applicable)
   - Fill in the blanks (if applicable)
   - True/False (if applicable)
   - Matching (if applicable)
   - Numerical problems (if applicable)
   - Multiple choice (if applicable) - MUST start with [MULTIPLE CHOICE]
   - Diagram-based (where appropriate) - MUST include [DIAGRAM REQUIRED]
   - Table-based (where appropriate) - MUST include [TABLE REQUIRED]
   - Case study (for higher grades)

3. Formatting Rules:
   - Each question must end with marks in square brackets like [2], [5]
   - For diagram questions, include: "[DIAGRAM REQUIRED]"
   - For table questions, include: "[TABLE REQUIRED]"
   - For multiple choice questions, start with: "[MULTIPLE CHOICE]"
   - One question per line, no numbering
   - Use LaTeX formatting for math: $E=mc^2$
   - For chemical equations: \\ce{{H2O}}
   - For units: \\SI{{5}}{{\\meter\\per\\second}}
   - For percentages: 75\\%
   - For currency: Rs. 150 or \\$150

4. Content Guidelines:
   - Cover major syllabus topics
   - Include real-world application questions
   - Use grade appropriate language
   - Vary question types appropriately
   - Ensure that around 10% of questions are multiple choice. MCQs should always be at the start of the paper. 
     Format for MCQs:
        [MULTIPLE CHOICE] Question text [1] [Remember]
        [A] Option A
        [B] Option B
        [C] Option C
        [D] Option D

5. Critical Thinking Focus:
   - Ensure proper difficulty progression
   - No additional text or explanations
   - Prioritize higher-order thinking skills
   - Include synthesis-based questions, data analysis, and scenario evaluation

6. CUSTOM INSTRUCTIONS:
{custom_instructions}

Sample Formats:
- "State the law of conservation of energy. [1] [Remember]"
- "Solve for x: $2x + 5 = 15$ showing all steps. [2] [Apply]"
- "Explain the process of photosynthesis with a labeled diagram. [5] [Understand] [DIAGRAM REQUIRED]"
- "Analyze the given economic data and answer the questions: [TABLE REQUIRED] [4] [Analyze]"
- "Compare and contrast mitosis and meiosis. [3] [Evaluate]"
- "[MULTIPLE CHOICE] Which of the following is a renewable resource? [1] [Remember]
        [A] Coal
        [B] Solar
        [C] Natural Gas
        [D] Nuclear"

Syllabus Context (Use only this syllabus as your knowledge base):
{syllabus_text if syllabus_text else 'No specific syllabus provided'}

Sample Reference / Blueprint (Use this as your guide. If sample paper, replicate the same format):
{sample_text if sample_text else 'No sample papers provided'}
"""
    try:
        logger.info("Calling Gemini API for question generation")
        response = None
        try:
            if client and hasattr(client, 'models'):
                # Using new genai client
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_modalities=['TEXT'])
                )
            elif GENAI_AVAILABLE:
                # Using standard google.generativeai
                model = genai.GenerativeModel(GEMINI_MODEL)
                response = model.generate_content(prompt)
            else:
                logger.error("Google Generative AI not available")
                return ""
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return ""
        text = None
        try:
            if response and hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                content = getattr(candidate, 'content', None)
                parts = getattr(content, 'parts', None)
                if parts and hasattr(parts[0], 'text'):
                    text = parts[0].text.strip()
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")
            text = None
        logger.info("Successfully generated questions")
        return text or ""
    except Exception as e:
        logger.error(f"Question generation error: {e}\n{traceback.format_exc()}")
        return f"Error generating questions: {e}"


def select_questions_from_bank_with_ai(
    questions: List[str], 
    num_questions: int, 
    grade: str, 
    subject: str, 
    total_marks: int,
    difficulty_split: dict, 
    board: str, 
    blooms_levels: list, 
    custom_instructions: str,
    blueprint_text: Optional[str] = None
) -> str:
    """
    Use AI to intelligently select questions from a question bank based on paper requirements.
    """
    logger.info(f"Using AI to select {num_questions} questions from bank of {len(questions)} questions")
    
    try:
        # Prepare the question bank text
        questions_text = "\n\n".join([f"Question {i+1}: {q}" for i, q in enumerate(questions)])
        
        # Build the AI prompt for intelligent question selection
        prompt = f"""You are an expert educator tasked with selecting the most appropriate questions from a question bank to create a well-balanced exam paper.

**Paper Requirements:**
- Grade: {grade}
- Subject: {subject}
- Board: {board}
- Total Marks: {total_marks}
- Number of Questions: {num_questions}
- Difficulty Distribution: Easy: {difficulty_split.get('easy', 0)}%, Medium: {difficulty_split.get('medium', 0)}%, Hard: {difficulty_split.get('hard', 0)}%
- Bloom's Taxonomy Levels: {', '.join(blooms_levels) if blooms_levels else 'Not specified'}

**Custom Instructions:**
{custom_instructions if custom_instructions else 'None provided'}

**Paper Blueprint/Structure:**
{blueprint_text if blueprint_text else 'No specific blueprint provided - use standard academic paper structure'}

**Available Question Bank:**
{questions_text}

**Task:**
Select exactly {num_questions} questions from the above question bank that best match the paper requirements. Consider:

1. **Difficulty Balance**: Ensure the selected questions match the specified difficulty distribution
2. **Content Coverage**: Select questions that cover different topics/concepts appropriately
3. **Question Types**: Include a good mix of question types (MCQ, short answer, long answer, etc.)
4. **Bloom's Taxonomy**: If specified, ensure questions align with the cognitive levels
5. **Blueprint Alignment**: If a blueprint is provided, follow its structure and requirements
6. **Mark Distribution**: Ensure the total marks align with the paper requirements

**Output Format:**
Return only the selected questions in their original format, numbered sequentially from 1 to {num_questions}. Do not add any additional commentary or explanations.

**Selected Questions:**"""

        # Generate response using Gemini
        if GENAI_AVAILABLE:
            if hasattr(genai, 'GenerativeModel'):
                model = genai.GenerativeModel(GEMINI_MODEL)
                response = model.generate_content(prompt)
                selected_questions = response.text
            else:
                # Fallback for older API
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[{"parts": [{"text": prompt}]}]
                )
                selected_questions = response.candidates[0].content.parts[0].text
        else:
            logger.error("Gemini API not available")
            raise ValueError("AI question selection is unavailable. Use the validated school platform bank selector.")

        logger.info("AI question selection completed successfully")
        return selected_questions

    except Exception as e:
        logger.error(f"Error in AI question selection: {e}")
        raise ValueError("Question bank selection failed; no random fallback is permitted.") from e
