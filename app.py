from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List
from pydantic import BaseModel
import logging
from dotenv import load_dotenv
from utils import get_html_content, setup_oauth_via_http, init_pocketbase


# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI()

# Pydantic models for request validation
class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    cooking_level: Optional[str] = None
    dietary_preferences: Optional[List[str]] = None

# Initialize database connection
pb = init_pocketbase()
setup_oauth_via_http()

# FastAPI routes
@app.get("/landing", response_class=HTMLResponse)
async def read_root():
    return get_html_content("index.html")

@app.get("/", response_class=HTMLResponse)
async def read_signup():
    return get_html_content("signup.html")