import os
import asyncio
import pandas as pd
import logging
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from utils import (
    bot, update_csv_files, DOCUMENTS_CSV, SHIPMENTS_CSV, TRACEABILITY_CSV,
    init_pocketbase, setup_oauth_via_http, fetch_pocketbase_config, init_groq_client, get_groq_model
)
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI()

# Get CORS settings from environment variables
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get frontend paths from environment variables
FRONTEND_DIR = os.getenv("FRONTEND_DIR", "Frontend")
LANDING_DIR = os.getenv("LANDING_DIR", "Landing")

# Initialize clients on startup
pb_client = None
groq_client = None

@app.on_event("startup")
async def startup_event():
    """Initialize clients on startup"""
    global pb_client, groq_client
    
    # Initialize PocketBase client
    try:
        pb_client = init_pocketbase()
        if pb_client:
            logger.info("PocketBase client initialized successfully")
            
            # Set up OAuth
            oauth_result = setup_oauth_via_http()
            if oauth_result:
                logger.info("OAuth configured successfully")
            else:
                logger.warning("OAuth configuration failed or was already configured")
    except Exception as e:
        logger.error(f"Error initializing PocketBase: {str(e)}")
    
    # Initialize Groq client
    try:
        groq_client = init_groq_client()
        if groq_client:
            logger.info("Groq client initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing Groq client: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return FileResponse(f"{FRONTEND_DIR}/signup.html")

@app.get("/landing", response_class=HTMLResponse)
async def get_index():
    return FileResponse(f"{FRONTEND_DIR}/index.html")

@app.post("/upload_csv")
async def upload_csv(
    documents_csv: UploadFile = File(None),
    shipments_csv: UploadFile = File(None),
    traceability_csv: UploadFile = File(None)
):
    files = {}
    if documents_csv:
        files["documents_csv"] = documents_csv
    if shipments_csv:
        files["shipments_csv"] = shipments_csv
    if traceability_csv:
        files["traceability_csv"] = traceability_csv
    if not files:
        return JSONResponse({"message": "No files provided."})
    updated = await update_csv_files(files)
    if updated:
        return JSONResponse({"message": "CSV files updated successfully."})
    else:
        return JSONResponse({"message": "No valid CSV files uploaded."})

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    message = data.get("message", "")
    exporter_id = data.get("exporter_id", None)

    async def stream_response():
        # The bot.process_query now yields structured JSON data
        async for chunk in bot.process_query(message, exporter_id):
            yield chunk

    return StreamingResponse(stream_response(), media_type="text/plain")

@app.get("/new_chat")
async def new_chat():
    return JSONResponse({"message": "New chat window opened. Chat history cleared."})

@app.get("/list_csv")
async def list_csv():
    files = {
        "documents_csv": os.path.exists(DOCUMENTS_CSV),
        "shipments_csv": os.path.exists(SHIPMENTS_CSV),
        "traceability_csv": os.path.exists(TRACEABILITY_CSV)
    }
    return JSONResponse({"files": files})

@app.get("/list_exporters")
async def list_exporters():
    # Get exporters from profiles
    profile_exporters = [
        {
            "exporter_id": exporter_id,
            "exporter_name": data.get("Exporter Name", "Unknown"),
            "country": data.get("Country of Origin", "Unknown"),
            "industry": data.get("Industry Focus", "Unknown"),
            "has_profile": True
        }
        for exporter_id, data in bot.exporter_profiles.items()
    ]
    
    # Get unique exporters from CSV files
    csv_exporters = set()
    exporter_names = {}
    
    try:
        if os.path.exists(DOCUMENTS_CSV):
            # Handle BOM and double quotes in CSV
            docs_df = pd.read_csv(DOCUMENTS_CSV, encoding='utf-8-sig')
            # Get the actual Exporter ID column name (might have extra quotes)
            exporter_id_col = [col for col in docs_df.columns if 'Exporter ID' in col][0]
            exporter_name_col = [col for col in docs_df.columns if 'Exporter Name' in col][0]
            
            if not docs_df.empty and exporter_id_col in docs_df.columns:
                # Clean the exporter IDs of any quotes
                clean_ids = docs_df[exporter_id_col].astype(str).apply(lambda x: x.strip('"'))
                csv_exporters.update(clean_ids.dropna().unique())
                # Store exporter names
                for idx, row in docs_df.iterrows():
                    eid = str(row[exporter_id_col]).strip('"')
                    name = str(row[exporter_name_col]).strip('"')
                    exporter_names[eid] = name
    except Exception as e:
        logger.error(f"Error reading documents CSV: {str(e)}")
    
    # Add CSV-only exporters (those without profiles)
    profile_ids = {exp["exporter_id"] for exp in profile_exporters}
    csv_only_exporters = [
        {
            "exporter_id": str(exporter_id),
            "exporter_name": exporter_names.get(str(exporter_id), "Unknown"),
            "country": "Unknown",
            "industry": "Unknown",
            "has_profile": False
        }
        for exporter_id in csv_exporters
        if str(exporter_id) not in profile_ids
    ]
    
    # Combine both lists
    all_exporters = profile_exporters + csv_only_exporters
    
    # Sort by exporter ID
    all_exporters.sort(key=lambda x: x["exporter_id"])
    
    # If no exporters found, return an empty list rather than error
    if not all_exporters:
        return JSONResponse({
            "exporters": [],
            "total_count": 0,
            "profile_count": 0,
            "csv_only_count": 0
        })
    
    return JSONResponse({
        "exporters": all_exporters,
        "total_count": len(all_exporters),
        "profile_count": len(profile_exporters),
        "csv_only_count": len(csv_only_exporters)
    })

# New endpoints for PocketBase and Groq integration
@app.get("/api/pocketbase/status")
async def get_pocketbase_status():
    """Get the current status of the PocketBase connection"""
    try:
        config = fetch_pocketbase_config()
        return JSONResponse(config)
    except Exception as e:
        logger.error(f"Error getting PocketBase status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pocketbase/setup-oauth")
async def setup_pocketbase_oauth():
    """Set up OAuth for PocketBase"""
    try:
        result = setup_oauth_via_http()
        if result:
            return JSONResponse({"status": "success", "message": "OAuth configured successfully"})
        else:
            return JSONResponse(
                {"status": "error", "message": "Failed to configure OAuth"}, 
                status_code=500
            )
    except Exception as e:
        logger.error(f"Error setting up OAuth: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/groq/status")
async def get_groq_status():
    """Check if Groq API is configured and working"""
    global groq_client
    
    if not groq_client:
        try:
            groq_client = init_groq_client()
        except Exception as e:
            logger.error(f"Error initializing Groq client: {str(e)}")
            return JSONResponse(
                {"status": "error", "message": f"Failed to initialize Groq client: {str(e)}"},
                status_code=500
            )
    
    if not groq_client:
        return JSONResponse(
            {"status": "error", "message": "Groq client not initialized. Check API key."},
            status_code=500
        )
    
    try:
        # Test the Groq API with a simple completion
        model = get_groq_model()
        response = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello, are you working?"}],
            max_tokens=10
        )
        return JSONResponse({
            "status": "success", 
            "message": "Groq API is working",
            "model": response.model
        })
    except Exception as e:
        logger.error(f"Error testing Groq API: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": f"Failed to test Groq API: {str(e)}"},
            status_code=500
        )

if __name__ == '__main__':
    import uvicorn
    # Get host and port from environment variables
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host=HOST, port=PORT)
