import os
import pandas as pd
import json
import anthropic
from anthropic.types import ContentBlock, ToolUseBlock, TextBlock

# CSV file paths
DOCUMENTS_CSV = "documents.csv"
SHIPMENTS_CSV = "shipments.csv" 
TRACEABILITY_CSV = "traceability_records.csv"

# Set the API key and model
ANTHROPIC_API_KEY = "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"
MODEL = "claude-3-5-sonnet-20241022"

class FDAComplianceBot:
    def __init__(self):
        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = MODEL
        
        # Initialize exporter profiles dictionary
        self.exporter_profiles = {}
        
        # Try to load CSV data if available
        try:
            print("Loading reference data...")
            self.documents_df = pd.read_csv(DOCUMENTS_CSV)
            self.shipments_df = pd.read_csv(SHIPMENTS_CSV)
            self.traceability_df = pd.read_csv(TRACEABILITY_CSV)
            print("Reference data loaded successfully")
        except Exception as e:
            print(f"Warning: Could not load reference data: {e}")
            print("Continuing without reference data...")
            self.documents_df = pd.DataFrame()
            self.shipments_df = pd.DataFrame()
            self.traceability_df = pd.DataFrame()
        
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

    def create_system_prompt(self):
        """Create a system prompt for Claude"""
        # Convert DataFrames to formatted text if they exist
        documents_text = ""
        shipments_text = ""
        traceability_text = ""
        
        if not self.documents_df.empty:
            documents_text = "DOCUMENT RECORDS:\n" + self.documents_df.to_string(index=False)
        
        if not self.shipments_df.empty:
            shipments_text = "SHIPMENT RECORDS:\n" + self.shipments_df.to_string(index=False)
        
        if not self.traceability_df.empty:
            traceability_text = "TRACEABILITY RECORDS:\n" + self.traceability_df.to_string(index=False)
        
        # Create system prompt with FDA requirements
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
        # Generate an exporter ID if not provided
        if not exporter_id:
            existing_ids = self.exporter_profiles.keys()
            if existing_ids:
                last_id_num = max([int(eid.replace("EX", "")) for eid in existing_ids])
                exporter_id = f"EX{last_id_num + 1:03d}"
            else:
                exporter_id = "EX001"
        
        # Create exporter profile
        self.exporter_profiles[exporter_id] = {
            "Exporter ID": exporter_id,
            "Exporter Name": exporter_name,
            "Country of Origin": country_of_origin,
            "Industry Focus": industry_focus,
            "Operation Size": operation_size,
            "Tech Level": tech_level,
            "Export Frequency": export_frequency,
            "Shipping Modalities": shipping_modalities
        }
        
        return self.exporter_profiles[exporter_id]

    def get_active_exporter_id(self, exporter_id=None):
        """Get active exporter ID or check if provided ID exists"""
        if exporter_id and exporter_id in self.exporter_profiles:
            return exporter_id
        elif len(self.exporter_profiles) == 1:
            # If there's only one exporter, return that ID
            return list(self.exporter_profiles.keys())[0]
        return None

    def process_query(self, query, exporter_id=None):
        """Process user query using Claude with function calling and streaming"""
        # Check if we have the exporter profile
        active_exporter_id = self.get_active_exporter_id(exporter_id)
        
        # Prepare messages
        messages = [{"role": "user", "content": query}]
        
        # Add exporter context if available
        if active_exporter_id and active_exporter_id in self.exporter_profiles:
            exporter_profile = self.exporter_profiles[active_exporter_id]
            exporter_context = f"ACTIVE EXPORTER:\n{json.dumps(exporter_profile, indent=2)}\n\n"
            
            # Add any reference data for this exporter
            if not self.documents_df.empty:
                exporter_docs = self.documents_df[self.documents_df["Exporter ID"] == active_exporter_id]
                if not exporter_docs.empty:
                    exporter_context += f"EXPORTER DOCUMENTS:\n{exporter_docs.to_string(index=False)}\n\n"
            
            if not self.shipments_df.empty:
                exporter_shipments = self.shipments_df[self.shipments_df["Exporter ID"] == active_exporter_id]
                if not exporter_shipments.empty:
                    exporter_context += f"EXPORTER SHIPMENTS:\n{exporter_shipments.to_string(index=False)}\n\n"
            
            if not self.traceability_df.empty:
                exporter_records = self.traceability_df[self.traceability_df["Exporter ID"] == active_exporter_id]
                if not exporter_records.empty:
                    exporter_context += f"EXPORTER TRACEABILITY RECORDS:\n{exporter_records.to_string(index=False)}\n\n"
            
            # Add context to system prompt
            system_with_context = self.system_prompt + "\n\n" + exporter_context
        else:
            system_with_context = self.system_prompt
        
        # Call Claude with streaming
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=2000,
                system=system_with_context,
                messages=messages,
                tools=self.tools
            ) as stream:
                # Track tool use for follow-up
                found_tool_use = False
                tool_block = None
                
                # Print response in chunks
                print("\n🤖 ", end="", flush=True)
                full_text = ""
                
                for chunk in stream:
                    if chunk.type == "content_block_delta" and hasattr(chunk, "delta"):
                        if chunk.delta.type == "text_delta" and hasattr(chunk.delta, "text"):
                            print(chunk.delta.text, end="", flush=True)
                            full_text += chunk.delta.text
                    
                    # Check for tool use blocks
                    if not found_tool_use and chunk.type == "content_block_start":
                        if hasattr(chunk, "content_block") and chunk.content_block.type == "tool_use":
                            found_tool_use = True
                            tool_block = chunk.content_block
                
                print()  # End the line after response
                
                # If we found a tool use, handle it
                if found_tool_use and tool_block:
                    tool_name = tool_block.name
                    tool_id = tool_block.id
                    tool_input = tool_block.input
                    
                    print(f"\n(Using {tool_name} tool to gather more information...)")
                    
                    if tool_name == "collect_exporter_info":
                        # Process collect_exporter_info function call
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
                        
                        # Create tool response
                        tool_result = json.dumps({
                            "success": True,
                            "exporter_id": exporter_profile["Exporter ID"],
                            "exporter_name": exporter_profile["Exporter Name"],
                            "message": f"Exporter profile created successfully for {exporter_profile['Exporter Name']}"
                        })
                        
                        # Call Claude again with the tool response and stream the result
                        print(f"\nProfile created for {exporter_profile['Exporter Name']} (ID: {exporter_profile['Exporter ID']})")
                        print("\n🤖 ", end="", flush=True)
                        
                        with self.client.messages.stream(
                            model=self.model,
                            max_tokens=2000,
                            system=system_with_context,
                            messages=messages + [
                                {
                                    "role": "assistant",
                                    "content": [
                                        {
                                            "type": "tool_use",
                                            "id": tool_id,
                                            "name": tool_name,
                                            "input": tool_input
                                        }
                                    ]
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": tool_id,
                                            "content": tool_result
                                        }
                                    ]
                                }
                            ]
                        ) as follow_up_stream:
                            for chunk in follow_up_stream:
                                if chunk.type == "content_block_delta" and hasattr(chunk, "delta"):
                                    if chunk.delta.type == "text_delta" and hasattr(chunk.delta, "text"):
                                        print(chunk.delta.text, end="", flush=True)
                                        full_text += chunk.delta.text
                            
                            print()  # End the line
                        
                    elif tool_name == "analyze_compliance":
                        # Process analyze_compliance function call
                        exporter_id = tool_input.get("exporter_id")
                        analysis = self.analyze_compliance(exporter_id)
                        
                        # Create tool response
                        tool_result = json.dumps({
                            "success": True,
                            "exporter_id": exporter_id,
                            "analysis": analysis
                        })
                        
                        # Call Claude again with the tool response and stream the result
                        print(f"\nAnalyzing compliance for exporter {exporter_id}...")
                        print("\n🤖 ", end="", flush=True)
                        
                        with self.client.messages.stream(
                            model=self.model,
                            max_tokens=2000,
                            system=system_with_context,
                            messages=messages + [
                                {
                                    "role": "assistant",
                                    "content": [
                                        {
                                            "type": "tool_use",
                                            "id": tool_id,
                                            "name": tool_name,
                                            "input": tool_input
                                        }
                                    ]
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": tool_id,
                                            "content": tool_result
                                        }
                                    ]
                                }
                            ]
                        ) as follow_up_stream:
                            for chunk in follow_up_stream:
                                if chunk.type == "content_block_delta" and hasattr(chunk, "delta"):
                                    if chunk.delta.type == "text_delta" and hasattr(chunk.delta, "text"):
                                        print(chunk.delta.text, end="", flush=True)
                                        full_text += chunk.delta.text
                            
                            print()  # End the line
                
                return full_text
                
        except Exception as e:
            print(f"Error calling Claude API: {e}")
            return "I'm sorry, I encountered an error processing your request. Please try again."

    def analyze_compliance(self, exporter_id):
        """Analyze compliance status for an exporter"""
        if not exporter_id or exporter_id not in self.exporter_profiles:
            return "Exporter ID not found. Please provide a valid exporter ID."
        
        exporter_profile = self.exporter_profiles[exporter_id]
        
        # Check if we have reference data to analyze
        has_reference_data = False
        analysis_results = []
        
        # Check documents
        if not self.documents_df.empty:
            exporter_docs = self.documents_df[self.documents_df["Exporter ID"] == exporter_id]
            if not exporter_docs.empty:
                has_reference_data = True
                # Check for pending documents
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
        
        # Check shipments
        if not self.shipments_df.empty:
            exporter_shipments = self.shipments_df[self.shipments_df["Exporter ID"] == exporter_id]
            if not exporter_shipments.empty:
                has_reference_data = True
                # Check for non-compliant shipments
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
        
        # Check traceability records
        if not self.traceability_df.empty:
            exporter_records = self.traceability_df[self.traceability_df["Exporter ID"] == exporter_id]
            if not exporter_records.empty:
                has_reference_data = True
                # Check for failed records
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
        
        # Generate analysis text
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
            # Sort by severity
            analysis_results.sort(key=lambda x: 0 if x["severity"] == "High" else 1 if x["severity"] == "Medium" else 2)
            
            result_text = f"Compliance Analysis for {exporter_profile.get('Exporter Name')}:\n\n"
            result_text += f"Found {len(analysis_results)} compliance issues:\n\n"
            
            for i, issue in enumerate(analysis_results):
                result_text += f"{i+1}. {issue['severity']} Priority: {issue['issue_type']} {issue['id']} - {issue['status']}\n"
                result_text += f"   Details: {issue['details']}\n\n"
            
            # Add recommendations based on product type
            industry_focus = exporter_profile.get("Industry Focus", "")
            product_type = industry_focus.split(" – ")[0] if " – " in industry_focus else industry_focus
            
            result_text += "General Recommendations:\n"
            if "temperature" in str(analysis_results):
                result_text += "1. Implement more robust temperature monitoring throughout the supply chain\n"
            if "batch" in str(analysis_results) or "details" in str(analysis_results):
                result_text += "2. Ensure complete batch documentation with all required Key Data Elements\n"
            if "Non-Compliant" in str(analysis_results):
                result_text += "3. Review FDA traceability requirements for all shipments before departure\n"
            
            return result_text

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


def main():
    # Initialize chatbot
    print("Initializing FDA Compliance Chatbot...")
    bot = FDAComplianceBot()
    
    print("\n===== FDA COMPLIANCE CHATBOT =====")
    print("This chatbot helps exporters understand FDA Food Traceability requirements")
    print("Type 'exit' to quit\n")
    
    conversation_history = []
    current_exporter = None
    
    while True:
        # Show current exporter if any
        if current_exporter and current_exporter in bot.exporter_profiles:
            exporter_name = bot.exporter_profiles[current_exporter]["Exporter Name"]
            print(f"\nCurrent exporter: {exporter_name} ({current_exporter})")
        
        # Get user input
        user_input = input("\n👤 Your query: ")
        
        if user_input.lower() == 'exit':
            break
            
        # Check for exporter selection command
        if user_input.lower().startswith('select '):
            try:
                exporter_id = user_input.split(' ')[1]
                if exporter_id in bot.exporter_profiles:
                    current_exporter = exporter_id
                    exporter_name = bot.exporter_profiles[current_exporter]["Exporter Name"]
                    print(f"✅ Selected exporter: {exporter_name}")
                else:
                    print(f"❌ Exporter {exporter_id} not found")
                continue
            except:
                print("❌ Invalid selection format. Use 'select EX###'")
                continue
                
        # Check for list exporters command
        if user_input.lower() == 'list exporters':
            if bot.exporter_profiles:
                print("\nExporter Profiles:")
                for eid, profile in bot.exporter_profiles.items():
                    print(f"- {eid}: {profile['Exporter Name']} ({profile['Country of Origin']})")
            else:
                print("No exporter profiles created yet.")
            continue
            
        # Check if user is mentioning an exporter by name
        if not current_exporter and "comply" in user_input.lower() or "compliance" in user_input.lower():
            # Try to extract company name
            words = user_input.split()
            for i in range(len(words)-1):
                if words[i].lower() in ["for", "from", "about", "with"]:
                    possible_name = " ".join(words[i+1:])
                    possible_name = possible_name.strip().rstrip('?.,!')
                    if len(possible_name) > 3:  # Avoid short words
                        exporter_id = bot.find_exporter_by_name(possible_name)
                        if exporter_id:
                            current_exporter = exporter_id
                            print(f"Found exporter from your query: {bot.exporter_profiles[current_exporter]['Exporter Name']} ({current_exporter})")
        
        # Add user input to conversation history
        conversation_history.append({"role": "user", "content": user_input})
        
        # Process query - response is streamed within the function
        response_text = bot.process_query(user_input, current_exporter)
        
        # Add response to conversation history
        conversation_history.append({"role": "assistant", "content": response_text})


if __name__ == "__main__":
    main()