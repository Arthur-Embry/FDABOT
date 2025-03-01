import os
import asyncio
import pandas as pd
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from utils import bot, update_csv_files, DOCUMENTS_CSV, SHIPMENTS_CSV, TRACEABILITY_CSV

app = FastAPI()

# Allow CORS (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return FileResponse("index.html")

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
        print(f"Error reading documents CSV: {str(e)}")
    
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

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
