import re
from fractions import Fraction


def normalize_answer(value):
    """Exact numeric equivalence; no floating point tolerance or expression eval."""
    text = str(value).strip().replace('−','-').replace(',','.')
    if len(text) > 200:
        return None
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?(?:/[+-]?\d+)?', text):
        return None
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def answer_matches(task, value):
    normalized = normalize_answer(value)
    return normalized is not None and any(normalized == normalize_answer(a) for a in [task.answer, *task.accepted_answers])
