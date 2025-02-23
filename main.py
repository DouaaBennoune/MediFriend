from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import uvicorn
import json

# Initialize FastAPI app
app = FastAPI()

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Load Groq API Key
GROQ_API_KEY = "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"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"  # Updated URL

class HealthData(BaseModel):
    blood_pressure: str
    weight: float
    symptoms: str

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "diagnosis": None})

@app.post("/")
async def diagnose_form(
    request: Request,
    blood_pressure: str = Form(...),
    weight: float = Form(...),
    symptoms: str = Form(...)
):
    try:
        # Create HealthData instance
        data = HealthData(
            blood_pressure=blood_pressure,
            weight=weight,
            symptoms=symptoms
        )
        
        # Construct the prompt
        prompt = f"""
        Diagnose this patient:
        - Blood Pressure: {data.blood_pressure}
        - Weight: {data.weight} kg
        - Symptoms: {data.symptoms}
        
        1. What possible illness could they have?
        2. What values are normal, and what is not?
        3. Should they seek a doctor? Why?
        """
        
        # Request payload for Groq API
        payload = {
            "model": "mixtral-8x7b-32768",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        
        # Send request to Groq API
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        print("Sending request to Groq API...")
        print("URL:", GROQ_API_URL)
        print("Headers:", headers)
        print("Payload:", json.dumps(payload, indent=2))
        
        response = requests.post(GROQ_API_URL, json=payload, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Extract response
        response_data = response.json()
        print("API Response:", json.dumps(response_data, indent=2))
        
        diagnosis = response_data.get("choices", [{}])[0].get("message", {}).get("content", "No response")
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {str(e)}")
        diagnosis = f"An error occurred while connecting to the AI service: {str(e)}"
    except Exception as e:
        print(f"General error: {str(e)}")
        diagnosis = f"An unexpected error occurred: {str(e)}"
    
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "diagnosis": diagnosis}
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)