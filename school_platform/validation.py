"""Deterministic constraints shared by uploads, generation, and review."""
import hashlib
import re

TYPES = {'MCQ', 'Short Answer', 'Long Answer', 'Numerical', 'True/False'}
DIFFICULTIES = {'easy', 'medium', 'hard'}
BLOOMS = {'Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create'}
SLOT_FIELDS = {'type', 'marks', 'count', 'chapter', 'difficulty', 'bloom'}


def text(value, name, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{name} is required and must contain at most {maximum} characters.')
    return value.strip()


def positive(value, name, maximum=1000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f'{name} must be an integer between 1 and {maximum}.')
    return value


def fingerprint(stem):
    normalized = re.sub(r'[^\w]', '', stem.casefold())
    return hashlib.sha256(normalized.encode()).hexdigest()


def validate_blueprint(data):
    if not isinstance(data, dict):
        raise ValueError('Blueprint must be a JSON object.')
    allowed = {'grade', 'subject', 'board', 'academic_year', 'title', 'duration_minutes',
               'total_marks', 'num_questions', 'slots'}
    if set(data) - allowed:
        raise ValueError('Unsupported blueprint fields: ' + ', '.join(sorted(set(data) - allowed)))
    result = {key: text(data.get(key), key, 100) for key in
              ('grade', 'subject', 'board', 'academic_year', 'title')}
    result['duration_minutes'] = positive(data.get('duration_minutes'), 'Duration', 360)
    result['total_marks'] = positive(data.get('total_marks'), 'Total marks')
    result['num_questions'] = positive(data.get('num_questions'), 'Question count', 100)
    slots = data.get('slots')
    if not isinstance(slots, list) or not 1 <= len(slots) <= 100:
        raise ValueError('Provide 1–100 blueprint slots. All questions are compulsory in this version.')
    result['slots'] = []
    for slot in slots:
        if not isinstance(slot, dict) or set(slot) != SLOT_FIELDS:
            raise ValueError('Each slot requires exactly: ' + ', '.join(sorted(SLOT_FIELDS)))
        if any(not isinstance(slot[field], str) for field in ('type', 'difficulty', 'bloom')) or slot['type'] not in TYPES or slot['difficulty'] not in DIFFICULTIES or slot['bloom'] not in BLOOMS:
            raise ValueError('Invalid question type, difficulty, or Bloom level.')
        result['slots'].append(dict(slot, count=positive(slot['count'], 'Slot count', 100),
                                    marks=positive(slot['marks'], 'Slot marks', 100),
                                    chapter=text(slot['chapter'], 'Chapter', 120)))
    if sum(s['count'] for s in slots) != result['num_questions']:
        raise ValueError('Slot counts do not equal the requested number of questions.')
    if sum(s['count'] * s['marks'] for s in slots) != result['total_marks']:
        raise ValueError('Slot marks do not equal the requested total marks.')
    return result


def validate_question(q, passages=None):
    if not isinstance(q, dict):
        raise ValueError('Each question must be an object.')
    required = {'stem', 'type', 'marks', 'chapter', 'difficulty', 'bloom',
                'options', 'answer', 'solution', 'rubric', 'source_reference', 'source_quote'}
    if set(q) - (required | {'bank_id'}) or not required <= set(q):
        raise ValueError('Question fields do not match the required schema.')
    cleaned = dict(q)
    for field in ('stem', 'chapter', 'answer', 'solution'):
        cleaned[field] = text(q.get(field), field)
    if any(not isinstance(q[field], str) for field in ('type', 'difficulty', 'bloom')) or q['type'] not in TYPES or q['difficulty'] not in DIFFICULTIES or q['bloom'] not in BLOOMS:
        raise ValueError('Question has invalid classification.')
    positive(q['marks'], 'Question marks', 100)
    options = q['options']
    if not isinstance(options, list) or any(not isinstance(o, str) or not o.strip() for o in options):
        raise ValueError('Options must be a list of nonempty strings.')
    expected = 4 if q['type'] == 'MCQ' else 2 if q['type'] == 'True/False' else 0
    if len(options) != expected or len({o.strip().casefold() for o in options}) != len(options):
        raise ValueError('Question has missing or duplicate options.')
    if expected and q['answer'] not in options:
        raise ValueError('The answer must exactly match one of the options.')
    rubric = q['rubric']
    if not isinstance(rubric, list) or not rubric:
        raise ValueError('A marking rubric is required.')
    for item in rubric:
        if not isinstance(item, dict) or set(item) != {'criterion', 'marks'}:
            raise ValueError('Each rubric item needs criterion and marks.')
        text(item['criterion'], 'Rubric criterion')
        positive(item['marks'], 'Rubric marks', 100)
    if sum(item['marks'] for item in rubric) != q['marks']:
        raise ValueError('Rubric marks must equal question marks.')
    if not isinstance(q['source_reference'], str) or not isinstance(q['source_quote'], str):
        raise ValueError('Source reference and quote must be strings.')
    if passages is not None:
        reference = q['source_reference']
        quote = ' '.join(q['source_quote'].split())
        if reference not in passages or len(quote) < 20 or quote not in ' '.join(passages[reference].split()):
            raise ValueError('Source evidence must quote an existing approved passage exactly.')
    return cleaned


def matches(q, slot):
    return all(q.get(field) == slot[field] for field in SLOT_FIELDS - {'count'})


def select_bank_questions(candidates, blueprint, excluded=None):
    """Stable selection; exact slot categories make independent buckets feasible."""
    selected, used = [], set(excluded or [])
    for slot in blueprint['slots']:
        found = 0
        for candidate in candidates:
            q = validate_question(candidate)
            key = fingerprint(q['stem'])
            if key in used or not matches(q, slot):
                continue
            selected.append(q)
            used.add(key)
            found += 1
            if found == slot['count']:
                break
        if found != slot['count']:
            raise ValueError(f"Insufficient approved questions for {slot['chapter']}, {slot['type']}, "
                             f"{slot['marks']} marks, {slot['difficulty']}, {slot['bloom']}: "
                             f"need {slot['count']}, found {found} after recent-use exclusions.")
    validate_paper(selected, blueprint)
    return selected


def validate_paper(questions, blueprint, passages=None):
    if not isinstance(questions, list) or not questions:
        raise ValueError('Paper questions must be a nonempty list.')
    for question in questions:
        validate_question(question, passages)
    if len(questions) != blueprint['num_questions']:
        raise ValueError('Generated question count does not match the blueprint.')
    if sum(q['marks'] for q in questions) != blueprint['total_marks']:
        raise ValueError('Generated marks do not match the blueprint.')
    seen = set()
    offset = 0
    for slot in blueprint['slots']:
        for question in questions[offset:offset + slot['count']]:
            validate_question(question, passages)
            if not matches(question, slot):
                raise ValueError('A generated question does not match its assigned slot.')
            key = fingerprint(question['stem'])
            if key in seen:
                raise ValueError('Duplicate questions are not allowed.')
            seen.add(key)
        offset += slot['count']
    return True
