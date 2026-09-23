import json

from . import config
from .enterprise import metadata_for as enterprise_metadata_for

CATALOG = json.loads(config.SEMANTIC_PATH.read_text(encoding='utf-8'))


def retrieve(question: str) -> dict:
    scores = []
    for code, metric in CATALOG['metrics'].items():
        score = sum(1 for term in [metric['name'], *metric['synonyms']] if term in question)
        scores.append((score, code))
    matched = [code for score, code in sorted(scores, reverse=True) if score]
    # All five capability definitions remain available; ranked candidates are hints,
    # never a confidence gate that would discard a supported question.
    return {'ranked_metrics': matched, 'metrics': CATALOG['metrics'],
            'conventions': CATALOG['conventions'], 'calendar': CATALOG['calendar']}


def metadata_for(metric: str) -> dict:
    return enterprise_metadata_for(metric, CATALOG)
