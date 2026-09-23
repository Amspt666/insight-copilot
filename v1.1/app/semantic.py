import json

from . import config

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
    names = CATALOG['metrics'][metric]['tables']
    return {'metric': CATALOG['metrics'][metric],
            'tables': {name: CATALOG['tables'][name] for name in names},
            'joins': [j for j in CATALOG['joins'] if j['left'] in names and j['right'] in names]}
