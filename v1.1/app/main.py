from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, database, pipeline
from .llm import ModelError
from .models import AskRequest
from .planner import PlanError
from .semantic import CATALOG

app = FastAPI(title='InsightCopilot Finance', version='1.1.0', docs_url='/api/docs')
WEB = config.ROOT / 'web'
app.mount('/static', StaticFiles(directory=WEB), name='static')


@app.exception_handler(ModelError)
async def model_error(request, error):
    return JSONResponse(status_code=503, content={'status': 'error', 'message': str(error)})


@app.exception_handler(database.DataError)
async def data_error(request, error):
    return JSONResponse(status_code=422, content={'status': 'error', 'message': str(error)})


@app.exception_handler(PlanError)
async def plan_error(request, error):
    return JSONResponse(status_code=422, content={'status': 'error', 'message': str(error)})


@app.get('/')
def index():
    return FileResponse(WEB / 'index.html')


@app.get('/favicon.ico', include_in_schema=False)
def favicon():
    return FileResponse(WEB / 'favicon.svg', media_type='image/svg+xml')


@app.get('/api/health')
def health():
    return {'version': '1.1.0', 'database_ready': config.DB_PATH.exists(),
            'model_configured': bool(config.API_KEY), 'model': config.MODEL,
            'model_connectivity': 'not_checked', 'simulated': True}


@app.get('/api/catalog')
def catalog():
    return {**CATALOG, 'allowed_companies': config.ALLOWED_COMPANIES}


@app.get('/api/customers')
def customers():
    return database.customers()


@app.post('/api/ask')
def ask(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(422, detail='问题不能为空。')
    return pipeline.ask(request)

