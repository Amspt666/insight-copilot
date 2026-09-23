from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
for env_file in (ROOT / '.env', ROOT.parent / 'v1.1' / '.env', ROOT.parent / '.env', ROOT.parent / 'backend' / '.env'):
    load_dotenv(env_file, override=False)

DB_PATH = ROOT / 'data' / 'finance.sqlite'
SEMANTIC_PATH = ROOT / 'data' / 'semantic.json'
LINEAGE_PATH = ROOT / 'data' / 'lineage_relations.csv'
ENTERPRISE_CONFIG_PATH = ROOT / 'data' / 'enterprise_config.json'
BASE_URL = os.getenv('LLM_BASE_URL', 'https://api.deepseek.com').rstrip('/')
API_KEY = os.getenv('LLM_API_KEY') or os.getenv('DEEPSEEK_API_KEY', '')
MODEL = os.getenv('LLM_MODEL', 'deepseek-chat')
TIMEOUT = max(5, min(float(os.getenv('LLM_TIMEOUT', '60')), 180))
RETRIES = max(1, min(int(os.getenv('LLM_MAX_RETRIES', '2')), 3))
SQL_TIMEOUT = max(1, min(float(os.getenv('FIN_SQL_TIMEOUT', '5')), 15))
ALLOWED_COMPANIES = tuple(x.strip() for x in os.getenv('FIN_ALLOWED_COMPANIES', '1000,2000').split(',') if x.strip() in ('1000', '2000'))
if not ALLOWED_COMPANIES:
    raise ValueError('FIN_ALLOWED_COMPANIES must include 1000 or 2000')
