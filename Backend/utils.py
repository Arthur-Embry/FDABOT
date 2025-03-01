import os
import pandas as pd
import json
import time  # For synchronous sleep
import asyncio
import threading
import requests
import logging
import anthropic
from anthropic.types import ContentBlock, ToolUseBlock, TextBlock
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pocketbase import PocketBase
from groq import Groq

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# CSV file paths - load from env or use defaults
CSV_DIR = os.getenv("CSV_DIR", "CSV")
DOCUMENTS_CSV = os.path.join(CSV_DIR, os.getenv("DOCUMENTS_CSV", "documents.csv"))
SHIPMENTS_CSV = os.path.join(CSV_DIR, os.getenv("SHIPMENTS_CSV", "shipments.csv"))
TRACEABILITY_CSV = os.path.join(CSV_DIR, os.getenv("TRACEABILITY_CSV", "traceability_records.csv"))

# Set the API key and model from environment variables
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

# PocketBase and Groq utility functions
def init_pocketbase():
    """Initialize PocketBase connection with admin authentication"""
    pb_url = os.getenv('POCKETBASE_URL')
    admin_email = os.getenv('POCKETBASE_ADMIN_EMAIL')
    admin_password = os.getenv('POCKETBASE_ADMIN_PASSWORD')
    
    pb = PocketBase(pb_url)
    try:
        pb.admins.auth_with_password(admin_email, admin_password)
        logger.info("Successfully authenticated with PocketBase using SDK")
    except Exception as e:
        logger.error(f"Failed to authenticate with PocketBase using SDK: {str(e)}")
    return pb

def setup_oauth_via_http():
    """Set up OAuth providers for the users collection using raw HTTP requests"""
    pb_url = "https://pb-fda-channel.operatorai.com"
    admin_email = os.getenv('POCKETBASE_ADMIN_EMAIL')
    admin_password = os.getenv('POCKETBASE_ADMIN_PASSWORD')
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    try:
        # Authenticate as admin
        auth_response = requests.post(
            f"{pb_url}/api/collections/_superusers/auth-with-password",
            headers={"Content-Type": "application/json", "Accept": "*/*"},
            json={"identity": admin_email, "password": admin_password}
        )
        
        if not auth_response.ok:
            logger.error(f"Admin auth failed: {auth_response.status_code}")
            return False
        
        token = auth_response.json().get('token', '')
        if not token:
            return False
        
        # Set up headers for subsequent requests
        headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "*/*"
        }
        
        # Find users collection
        collections_response = requests.get(f"{pb_url}/api/collections", headers=headers)
        if not collections_response.ok:
            return False
        
        # Find users auth collection
        auth_collection = None
        for collection in collections_response.json().get('items', []):
            if collection.get('type') == 'auth' and collection.get('name') == 'users':
                auth_collection = collection
                break
        
        if not auth_collection:
            return False
        
        collection_id = auth_collection.get('id')
        
        # Get collection details
        collection_response = requests.get(
            f"{pb_url}/api/collections/{collection_id}",
            headers=headers
        )
        
        if not collection_response.ok:
            return False
        
        collection_data = collection_response.json()
        
        # Check if already configured
        oauth2_config = collection_data.get('oauth2', {})
        if oauth2_config.get('enabled') and oauth2_config.get('providers'):
            for provider in oauth2_config.get('providers', []):
                if provider.get('name') == 'google' and provider.get('clientId'):
                    return True
        
        # Update OAuth configuration
        collection_data['oauth2'] = {
            "enabled": True,
            "providers": [{"name": "google", "clientId": client_id, "clientSecret": client_secret}],
            "mappedFields": {"id": "", "name": "name", "username": "", "avatarURL": "avatar"}
        }
        
        # Update collection
        update_response = requests.patch(
            f"{pb_url}/api/collections/{collection_id}",
            headers=headers,
            json=collection_data
        )
        
        return update_response.ok
        
    except Exception as e:
        logger.error(f"Error setting up OAuth: {str(e)}")
        return False

def fetch_pocketbase_config():
    """Return the current PocketBase configuration."""
    try:
        config = {
            "url": os.getenv('POCKETBASE_URL'),
            "status": "active"
        }
        
        # Optionally check if the server is reachable
        try:
            response = requests.get(f"{config['url']}/api/health", timeout=3)
            if response.ok:
                config["health"] = "ok"
            else:
                config["health"] = "error"
                config["status_code"] = response.status_code
        except Exception as e:
            config["health"] = "unreachable"
            config["error"] = str(e)
            
        return config
    except Exception as e:
        logger.error(f"Error fetching PocketBase config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration: {str(e)}")

def init_groq_client():
    """Initialize and return a Groq client"""
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        logger.error("GROQ_API_KEY environment variable not set")
        return None
    
    try:
        client = Groq(api_key=api_key)
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {str(e)}")
        return None

def get_groq_model():
    """Get the configured Groq model from environment variables"""
    return os.getenv('GROQ_MODEL', 'llama3-8b-8192')

class FDAComplianceBot:
    def __init__(self):
        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = MODEL

        # Initialize exporter profiles dictionary
        self.exporter_profiles = {}

        # Define required columns for each file type
        self.required_columns = {
            'documents': ['ExporterId', 'DocumentId', 'Status', 'Comments'],
            'shipments': ['ExporterId', 'ShipmentId', 'ComplianceStatus', 'ProductDescription', 'ArrivalPort'],
            'traceability': ['ExporterId', 'RecordId', 'ComplianceFlag', 'Comments']
        }

        print("Loading reference data...")
        
        # Create CSV directory if it doesn't exist
        os.makedirs(CSV_DIR, exist_ok=True)
        
        # Load CSVs with proper column parsing
        self.documents_df = self._load_csv_with_validation(
            DOCUMENTS_CSV, 
            self.required_columns['documents']
        )
        
        self.shipments_df = self._load_csv_with_validation(
            SHIPMENTS_CSV, 
            self.required_columns['shipments']
        )
        
        self.traceability_df = self._load_csv_with_validation(
            TRACEABILITY_CSV, 
            self.required_columns['traceability']
        )
        
        print("Reference data loaded successfully")
        print(f"Documents DataFrame columns: {list(self.documents_df.columns)}")
        print(f"Shipments DataFrame columns: {list(self.shipments_df.columns)}")
        print(f"Traceability DataFrame columns: {list(self.traceability_df.columns)}")

        # Create system prompt
        self.create_system_prompt()

        # Define tools for function calling
        self.tools = [
            {
                "name": "collect_exporter_info",
                "description": "Collect information about an exporter to create a profile",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "exporter_id": {
                            "type": "string",
                            "description": "Unique identifier for the exporter (e.g., EX001)"
                        },
                        "exporter_name": {
                            "type": "string",
                            "description": "Name of the exporting company"
                        },
                        "country_of_origin": {
                            "type": "string",
                            "description": "Country where the exporter is based"
                        },
                        "industry_focus": {
                            "type": "string",
                            "description": "Main food category and product specialization"
                        },
                        "operation_size": {
                            "type": "string",
                            "description": "Size of the operation (small, medium, large) and employee count"
                        },
                        "tech_level": {
                            "type": "string",
                            "description": "Level of technological sophistication for traceability"
                        },
                        "export_frequency": {
                            "type": "string",
                            "description": "How often the company exports to the US"
                        },
                        "shipping_modalities": {
                            "type": "string",
                            "description": "Methods used for shipping (air freight, ocean freight, etc.)"
                        }
                    },
                    "required": ["exporter_name", "country_of_origin", "industry_focus"]
                }
            },
            {
                "name": "analyze_compliance",
                "description": "Analyze compliance issues for a specific exporter",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "exporter_id": {
                            "type": "string",
                            "description": "Unique identifier for the exporter (e.g., EX001)"
                        }
                    },
                    "required": ["exporter_id"]
                }
            }
        ]

    def _load_csv_with_validation(self, file_path, required_columns):
        """
        Load CSV file with proper parsing of quoted column names and validation.
        """
        try:
            # First read the header line to properly parse column names
            with open(file_path, 'r') as f:
                header_line = f.readline().strip()
                
            # Split the header properly considering quotes
            import csv
            header_reader = csv.reader([header_line])
            column_names = next(header_reader)
            
            # Clean up column names (remove quotes and whitespace)
            column_names = [col.strip('"').strip() for col in column_names]
            
            # Read the CSV with the cleaned column names
            df = pd.read_csv(file_path, names=column_names, skiprows=1)
            
            # Check for required columns
            missing_columns = [col for col in required_columns if col not in column_names]
            if missing_columns:
                print(f"\nWarning: Missing required columns in {os.path.basename(file_path)}: {missing_columns}")
                print(f"Available columns: {column_names}")
            
            return df
        
        except Exception as e:
            print(f"Error loading {file_path}: {str(e)}")
            return pd.DataFrame()

    def create_system_prompt(self):
        """Create a system prompt for Claude"""
        documents_text = ""
        shipments_text = ""
        traceability_text = ""

        if not self.documents_df.empty:
            documents_text = "DOCUMENT RECORDS:\n" + self.documents_df.to_string(index=False)
        if not self.shipments_df.empty:
            shipments_text = "SHIPMENT RECORDS:\n" + self.shipments_df.to_string(index=False)
        if not self.traceability_df.empty:
            traceability_text = "TRACEABILITY RECORDS:\n" + self.traceability_df.to_string(index=False)

        self.system_prompt = f"""You are an intelligent FDA Food Traceability Compliance Assistant for exporters shipping food to the United States.

Your purpose is to help exporters understand and comply with the FDA Food Traceability Final Rule. You should provide clear, accurate information about the rule's requirements, applicability, and implementation.

Key facts about the FDA Food Traceability Rule:
1. It applies to foods on the Food Traceability List (FTL), including certain fruits, vegetables, seafood, dairy, and ready-to-eat foods.
2. It requires recordkeeping of Key Data Elements (KDEs) at Critical Tracking Events (CTEs).
3. CTEs include growing, receiving, transforming, creating, and shipping foods.
4. The compliance deadline is January 20, 2026.
5. Records must be maintained for 2 years and provided to FDA within 24 hours if requested.

Common foods on the Food Traceability List (FTL):
- Fresh cut fruits and vegetables
- Fresh leafy greens (including romaine lettuce)
- Fresh herbs
- Tomatoes
- Peppers
- Sprouts
- Cucumbers
- Melons
- Tropical tree fruits
- Shell eggs
- Nut butters
- Fresh, frozen, or smoked finfish
- Fresh, frozen, or smoked crustaceans
- Fresh, frozen, or smoked molluscan shellfish
- Ready-to-eat deli salads
- Soft/semi-soft cheeses
- Fresh soft cheeses

{documents_text}

{shipments_text}

{traceability_text}

When responding to exporters:
1. If you don't have enough information about the exporter, use the collect_exporter_info function to gather necessary details.
2. Provide specific recommendations tailored to their product type, operation size, and technical capabilities.
3. Use clear, simple language to explain requirements.
4. Always cite the specific part of the FDA rule that applies to their situation.
5. If asked to analyze compliance, use the analyze_compliance function.

Never make up information about FDA requirements - if you're unsure, acknowledge the limitation and suggest the exporter consult the official FDA resources.
"""

    def collect_exporter_info(self, exporter_id=None, exporter_name=None, country_of_origin=None,
                              industry_focus=None, operation_size=None, tech_level=None,
                              export_frequency=None, shipping_modalities=None):
        """Store exporter information provided by function calling"""
        if not exporter_id:
            existing_ids = self.exporter_profiles.keys()
            if existing_ids:
                last_id_num = max([int(eid.replace("EX", "")) for eid in existing_ids])
                exporter_id = f"EX{last_id_num + 1:03d}"
            else:
                exporter_id = "EX001"

        # Don't create profile if we don't have minimum required information
        if not any([exporter_name, country_of_origin, industry_focus]):
            return {
                "Exporter ID": exporter_id,
                "status": "incomplete",
                "message": "Insufficient information to create profile"
            }

        self.exporter_profiles[exporter_id] = {
            "Exporter ID": exporter_id,
            "Exporter Name": exporter_name or "Unknown",
            "Country of Origin": country_of_origin or "Unknown",
            "Industry Focus": industry_focus or "Unknown",
            "Operation Size": operation_size or "Not specified",
            "Tech Level": tech_level or "Not specified",
            "Export Frequency": export_frequency or "Not specified",
            "Shipping Modalities": shipping_modalities or "Not specified"
        }
        return self.exporter_profiles[exporter_id]

    def get_active_exporter_id(self, exporter_id=None):
        """Get active exporter ID or check if provided ID exists"""
        if exporter_id and exporter_id in self.exporter_profiles:
            return exporter_id
        elif len(self.exporter_profiles) == 1:
            return list(self.exporter_profiles.keys())[0]
        return None

    def find_exporter_by_name(self, name):
        """Find an exporter by partial name match"""
        if not name:
            return None
        name_lower = name.lower()
        for exporter_id, profile in self.exporter_profiles.items():
            if name_lower in profile.get("Exporter Name", "").lower():
                return exporter_id
        # Also search in reference data if available
        if not self.documents_df.empty:
            for _, row in self.documents_df.iterrows():
                if name_lower in str(row.get("Exporter Name", "")).lower():
                    return row.get("Exporter ID")
        if not self.shipments_df.empty:
            for _, row in self.shipments_df.iterrows():
                if name_lower in str(row.get("Exporter Name", "")).lower():
                    return row.get("Exporter ID")
        return None

    def _process_query_sync(self, query, exporter_id=None):
        """
        Synchronous generator implementing the tool calling flow with structured message types.
        """
        active_exporter_id = self.get_active_exporter_id(exporter_id)
        messages = [{"role": "user", "content": query}]

        # Start with info message type
        yield json.dumps({"type": "metadata", "message_type": "info"}) + "\n"

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=2000,
                system=self.system_prompt,
                messages=messages,
                tools=self.tools
            ) as stream:
                found_tool_use = False
                tool_block = None
                full_text = ""
                current_message_type = "info"

                for chunk in stream:
                    if chunk.type == "content_block_delta" and hasattr(chunk, "delta"):
                        if chunk.delta.type == "text_delta" and hasattr(chunk.delta, "text"):
                            text = chunk.delta.text
                            print(text, end="", flush=True)
                            full_text += text
                            yield json.dumps({"type": "content", "text": text}) + "\n"

                    elif chunk.type == "content_block_start":
                        if hasattr(chunk, "content_block") and chunk.content_block.type == "tool_use":
                            found_tool_use = True
                            tool_block = chunk.content_block
                            
                            # Signal tool use is starting
                            yield json.dumps({
                                "type": "metadata", 
                                "message_type": "tool_use",
                                "tool": tool_block.name
                            }) + "\n"

                if found_tool_use and tool_block:
                    tool_name = tool_block.name
                    tool_id = tool_block.id
                    tool_input = tool_block.input

                    if tool_name == "collect_exporter_info":
                        # Create new section for tool usage
                        yield json.dumps({
                            "type": "metadata",
                            "message_type": "tool_use",
                            "tool": "collect_exporter_info"
                        }) + "\n"
                        yield json.dumps({
                            "type": "content",
                            "text": f"Collecting information about exporter...\n"
                        }) + "\n"

                        exporter_profile = self.collect_exporter_info(
                            exporter_id=tool_input.get("exporter_id"),
                            exporter_name=tool_input.get("exporter_name"),
                            country_of_origin=tool_input.get("country_of_origin"),
                            industry_focus=tool_input.get("industry_focus"),
                            operation_size=tool_input.get("operation_size"),
                            tech_level=tool_input.get("tech_level"),
                            export_frequency=tool_input.get("export_frequency"),
                            shipping_modalities=tool_input.get("shipping_modalities")
                        )

                        # Signal profile creation result
                        if exporter_profile.get("status") == "incomplete":
                            yield json.dumps({
                                "type": "metadata",
                                "message_type": "warning"
                            }) + "\n"
                        else:
                            yield json.dumps({
                                "type": "metadata",
                                "message_type": "profile_created",
                                "exporter_id": exporter_profile["Exporter ID"],
                                "exporter_name": exporter_profile.get("Exporter Name", "Unknown")
                            }) + "\n"

                        # Continue with follow-up stream
                        with self.client.messages.stream(
                            model=self.model,
                            max_tokens=2000,
                            system=self.system_prompt,
                            messages=messages + [
                                {
                                    "role": "assistant",
                                    "content": [{
                                        "type": "tool_use",
                                        "id": tool_id,
                                        "name": tool_name,
                                        "input": tool_input
                                    }]
                                },
                                {
                                    "role": "user",
                                    "content": [{
                                        "type": "tool_result",
                                        "tool_use_id": tool_id,
                                        "content": json.dumps(exporter_profile)
                                    }]
                                }
                            ]
                        ) as follow_up_stream:
                            # Reset message type for follow-up
                            yield json.dumps({"type": "metadata", "message_type": "info"}) + "\n"
                            
                            for chunk in follow_up_stream:
                                if chunk.type == "content_block_delta" and hasattr(chunk, "delta"):
                                    if chunk.delta.type == "text_delta" and hasattr(chunk.delta, "text"):
                                        text = chunk.delta.text
                                        print(text, end="", flush=True)
                                        yield json.dumps({"type": "content", "text": text}) + "\n"

                    elif tool_name == "analyze_compliance":
                        # Signal compliance analysis is starting
                        yield json.dumps({
                            "type": "metadata",
                            "message_type": "compliance_analysis",
                            "exporter_id": tool_input.get("exporter_id")
                        }) + "\n"

                        analysis = self.analyze_compliance(tool_input.get("exporter_id"))
                        
                        # Continue with compliance analysis stream
                        with self.client.messages.stream(
                            model=self.model,
                            max_tokens=2000,
                            system=self.system_prompt,
                            messages=messages + [
                                {
                                    "role": "assistant",
                                    "content": [{
                                        "type": "tool_use",
                                        "id": tool_id,
                                        "name": tool_name,
                                        "input": tool_input
                                    }]
                                },
                                {
                                    "role": "user",
                                    "content": [{
                                        "type": "tool_result",
                                        "tool_use_id": tool_id,
                                        "content": json.dumps({"analysis": analysis})
                                    }]
                                }
                            ]
                        ) as follow_up_stream:
                            # Set message type for compliance results
                            yield json.dumps({"type": "metadata", "message_type": "compliance"}) + "\n"
                            
                            for chunk in follow_up_stream:
                                if chunk.type == "content_block_delta" and hasattr(chunk, "delta"):
                                    if chunk.delta.type == "text_delta" and hasattr(chunk.delta, "text"):
                                        text = chunk.delta.text
                                        print(text, end="", flush=True)
                                        yield json.dumps({"type": "content", "text": text}) + "\n"

        except Exception as e:
            print(f"Error in _process_query_sync: {e}", flush=True)
            yield json.dumps({"type": "metadata", "message_type": "error"}) + "\n"
            yield json.dumps({"type": "content", "text": f"Error processing request: {str(e)}"}) + "\n"

    async def process_query(self, query, exporter_id=None):
        """
        Asynchronous generator that wraps the synchronous _process_query_sync
        using a background thread and an asyncio.Queue.
        """
        queue = asyncio.Queue()

        def run_in_thread():
            try:
                for chunk in self._process_query_sync(query, exporter_id):
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop = asyncio.get_running_loop()
        threading.Thread(target=run_in_thread, daemon=True).start()

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            # Ensure we yield bytes
            if isinstance(chunk, str):
                yield chunk.encode("utf-8")
            else:
                yield chunk

    def analyze_compliance(self, exporter_id):
        """Analyze compliance status for an exporter"""
        if not exporter_id or exporter_id not in self.exporter_profiles:
            return "Exporter ID not found. Please provide a valid exporter ID."

        exporter_profile = self.exporter_profiles[exporter_id]
        has_reference_data = False
        analysis_results = []

        if not self.documents_df.empty:
            exporter_docs = self.documents_df[self.documents_df["Exporter ID"] == exporter_id]
            if not exporter_docs.empty:
                has_reference_data = True
                pending_docs = exporter_docs[exporter_docs["Status"] == "Pending Review"]
                if not pending_docs.empty:
                    for _, doc in pending_docs.iterrows():
                        analysis_results.append({
                            "issue_type": "Document",
                            "id": doc["Document ID"],
                            "status": "Pending Review",
                            "details": doc["Comments"],
                            "severity": "Medium"
                        })

        if not self.shipments_df.empty:
            exporter_shipments = self.shipments_df[self.shipments_df["Exporter ID"] == exporter_id]
            if not exporter_shipments.empty:
                has_reference_data = True
                non_compliant = exporter_shipments[exporter_shipments["Compliance Status"] == "Non-Compliant"]
                if not non_compliant.empty:
                    for _, shipment in non_compliant.iterrows():
                        analysis_results.append({
                            "issue_type": "Shipment",
                            "id": shipment["Shipment ID"],
                            "status": "Non-Compliant",
                            "details": f"Non-compliant shipment of {shipment['Product Description']} to {shipment['Arrival Port']}",
                            "severity": "High"
                        })

        if not self.traceability_df.empty:
            exporter_records = self.traceability_df[self.traceability_df["Exporter ID"] == exporter_id]
            if not exporter_records.empty:
                has_reference_data = True
                failed_records = exporter_records[exporter_records["Compliance Flag"] == "Fail"]
                if not failed_records.empty:
                    for _, record in failed_records.iterrows():
                        analysis_results.append({
                            "issue_type": "Traceability Record",
                            "id": record["Record ID"],
                            "status": "Failed",
                            "details": record["Comments"],
                            "severity": "High"
                        })

        if not has_reference_data:
            industry_focus = exporter_profile.get("Industry Focus", "")
            product_type = industry_focus.split(" – ")[0] if " – " in industry_focus else industry_focus
            return f"""No reference data available for analysis. Based on profile information alone:

Exporter: {exporter_profile.get('Exporter Name')}
Product Type: {product_type}

Recommendations:
1. Implement traceability systems for all Critical Tracking Events (CTEs)
2. Ensure Key Data Elements (KDEs) are recorded for each CTE
3. Maintain documentation for at least 2 years
4. Establish procedures to provide records within 24 hours if requested by FDA
5. Review FDA's Food Traceability List to confirm product coverage"""
        elif not analysis_results:
            return f"""Compliance Analysis for {exporter_profile.get('Exporter Name')}:

No compliance issues found in the available reference data. All documents, shipments, and traceability records appear to be compliant with FDA requirements.

Recommendation: Continue current practices and stay updated on any FDA rule changes."""
        else:
            analysis_results.sort(key=lambda x: 0 if x["severity"] == "High" else 1 if x["severity"] == "Medium" else 2)
            result_text = f"Compliance Analysis for {exporter_profile.get('Exporter Name')}:\n\n"
            result_text += f"Found {len(analysis_results)} compliance issues:\n\n"
            for i, issue in enumerate(analysis_results):
                result_text += f"{i+1}. {issue['severity']} Priority: {issue['issue_type']} {issue['id']} - {issue['status']}\n"
                result_text += f"   Details: {issue['details']}\n\n"
            result_text += "General Recommendations:\n"
            if "temperature" in str(analysis_results):
                result_text += "1. Implement more robust temperature monitoring throughout the supply chain\n"
            if "batch" in str(analysis_results) or "details" in str(analysis_results):
                result_text += "2. Ensure complete batch documentation with all required Key Data Elements\n"
            if "Non-Compliant" in str(analysis_results):
                result_text += "3. Review FDA traceability requirements for all shipments before departure\n"
            return result_text

# Global instance of the bot used by the FastAPI app
bot = FDAComplianceBot()

async def update_csv_files(files):
    updated = False
    try:
        if 'documents_csv' in files:
            file_obj = files['documents_csv']
            contents = await file_obj.read()
            with open(DOCUMENTS_CSV, "wb") as f:
                f.write(contents)
            updated = True
            
        if 'shipments_csv' in files:
            file_obj = files['shipments_csv']
            contents = await file_obj.read()
            with open(SHIPMENTS_CSV, "wb") as f:
                f.write(contents)
            updated = True
            
        if 'traceability_csv' in files:
            file_obj = files['traceability_csv']
            contents = await file_obj.read()
            with open(TRACEABILITY_CSV, "wb") as f:
                f.write(contents)
            updated = True
            
        if updated:
            # Reinitialize the bot to reload CSV data with validation
            global bot
            bot = FDAComplianceBot()
            
        return updated
    except Exception as e:
        print(f"Error updating CSV files: {e}")
        return False
