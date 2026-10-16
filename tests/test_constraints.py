import copy
import pytest
from conftest import blueprint, question, questions
from school_platform.validation import validate_blueprint, validate_question, validate_paper, select_bank_questions
from school_platform.rendering import latex_text, render_latex


def test_valid_blueprint_and_paper():
    b=validate_blueprint(blueprint())
    assert validate_paper(questions(), b)


@pytest.mark.parametrize('change', [
    {'total_marks':11}, {'num_questions':5}, {'duration_minutes':0},
    {'unknown':'choice groups'}, {'total_marks':True}, {'slots':[]},
])
def test_invalid_blueprint(change):
    b=blueprint();b.update(change)
    with pytest.raises(ValueError):validate_blueprint(b)


@pytest.mark.parametrize('change', [
    {'options':['x','x','y','z']}, {'answer':'missing option'}, {'marks':0},
    {'rubric':[{'criterion':'incorrect total','marks':2}]}, {'difficulty':'impossible'},
])
def test_invalid_questions(change):
    q=question();q.update(change)
    with pytest.raises(ValueError):validate_question(q)


def test_citations_must_exist_and_match():
    q=question();passages={'page-12':q['source_quote']}
    validate_question(q,passages)
    with pytest.raises(ValueError):validate_question(q, {'page-13':q['source_quote']})
    q['source_quote']='This unsupported quote was invented by the model.'
    with pytest.raises(ValueError):validate_question(q,passages)


def test_selection_is_stable_and_fails_on_shortage():
    selected=select_bank_questions(questions(),blueprint())
    assert selected==questions()
    with pytest.raises(ValueError,match='Insufficient'):select_bank_questions(questions()[:2],blueprint())


def test_duplicate_question_is_rejected():
    qs=questions();qs[1]['stem']=qs[0]['stem']
    with pytest.raises(ValueError,match='Duplicate'):validate_paper(qs,blueprint())


@pytest.mark.parametrize('items',[None, {}, [], [{}], ['invalid question']])
def test_malformed_paper_fails_cleanly(items):
    with pytest.raises(ValueError):validate_paper(items,blueprint())


@pytest.mark.parametrize('expression', [r'$\input{secret}$',r'$\write18{command}$',r'$^^5cinput{secret}$'])
def test_executable_math_is_rejected(expression):
    with pytest.raises(ValueError):latex_text(expression)


def test_math_survives_rendering_and_prose_is_escaped():
    assert latex_text(r'Solve $\frac{1}{2}+x=3$ & explain.') == r'Solve $\frac{1}{2}+x=3$ \& explain.'
    output=render_latex({'blueprint':blueprint(),'questions':questions()},'Ashoka A')
    assert 'Correct fraction calculation' not in output
    assert 'Academic year: 2026' in output
