import os, requests, logging
from fastapi.responses import HTMLResponse
from groq import Groq
from pocketbase import PocketBase
from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

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
    pb_url = os.getenv('POCKETBASE_URL')
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

# Add this to utils.py (utility functions section)
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
    
def get_html_content(filename):
    try:
        with open(filename, "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content=f"{filename} not found", status_code=404)