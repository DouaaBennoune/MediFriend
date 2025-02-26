# views.py
import json
import re
import requests
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from .models import Patient

def home(request):
    """Render the main page with the patient form and queue"""
    return render(request, 'queue/index.html')

def get_queue(request):
    """API endpoint to get the current queue sorted by priority"""
    patients = Patient.objects.all().order_by('-priority', 'created_at')
    queue_data = []
    
    for patient in patients:
        queue_data.append({
            'id': patient.id,  # Added patient ID for frontend reference
            'name': patient.name,
            'email': patient.email,
            'age': patient.age,
            'cancer_stage': patient.cancer_stage,
            'therapy_type': patient.therapy_type,
            'temperature': patient.temperature,
            'heart_rate': patient.heart_rate,
            'blood_pressure': patient.blood_pressure,
            'description': patient.description,
            'priority': patient.priority,
            'appointment': patient.appointment.strftime("%Y-%m-%d %H:%M:%S"),
            'created_at': patient.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    return JsonResponse({'queue': queue_data})
@csrf_exempt
def add_patient(request):
    """API endpoint to add a new patient and get AI priority & appointment"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            required_fields = ['name', 'email', 'age', 'cancerStage', 'therapytype', 
                               'temp', 'heart', 'blood', 'description']
            for field in required_fields:
                if field not in data or not data[field]:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Missing required field: {field}'
                    }, status=400)
            
            # Get AI priority and appointment
            try:
                ai_response = get_ai_recommendation(data)
                priority = ai_response['priority']
                appointment_date = calculate_appointment(priority, ai_response.get('appointment'))
            except Exception as e:
                # Log the error but continue with fallback values
                print(f"AI recommendation error: {str(e)}")
                priority = calculate_priority_fallback(data)
                appointment_date = calculate_appointment(priority)
            
            # Create new patient
            patient = Patient(
                name=data['name'],
                email=data['email'],
                age=data['age'],
                cancer_stage=data['cancerStage'],
                therapy_type=data['therapytype'],
                temperature=data['temp'],
                heart_rate=data['heart'],
                blood_pressure=data['blood'],
                description=data['description'],
                priority=priority,
                appointment=appointment_date
            )
            patient.save()
            
            return JsonResponse({
                'success': True, 
                'priority': priority,
                'appointment': appointment_date.strftime("%Y-%m-%d %H:%M:%S")
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

def get_ai_recommendation(data):
    """Get both priority and appointment recommendation from Gemini AI"""
    api_key = "AIzaSyBsjF22MDVkvIuHSxwwVlmxo3iXjspMZo4"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    As an oncology AI specialist, analyze this patient data:
    - Age: {data['age']}
    - Cancer Stage: {data['cancerStage']}
    - Therapy Type: {data['therapytype']}
    - Vital Signs: Temperature {data['temp']}°C, Heart Rate {data['heart']} bpm, Blood Pressure {data['blood']}
    - Symptoms: {data['description']}

    Return ONLY a JSON object with:
    - "priority": 1-5 (1=lowest, 5=highest urgency)
    - "appointment": Recommended appointment date (YYYY-MM-DD)
    
    Example response:
    {{
        "priority": 3,
        "appointment": "2024-03-20"
    }}
    """
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        response_data = response.json()
        
        # Check if the response structure is as expected
        if ('candidates' not in response_data or 
            not response_data['candidates'] or 
            'content' not in response_data['candidates'][0] or
            'parts' not in response_data['candidates'][0]['content'] or
            not response_data['candidates'][0]['content']['parts'] or
            'text' not in response_data['candidates'][0]['content']['parts'][0]):
            raise Exception("Unexpected API response structure")
        
        response_text = response_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*?\}', response_text, re.DOTALL)
        if json_match:
            try:
                ai_data = json.loads(json_match.group(0))
                return {
                    'priority': validate_priority(ai_data.get('priority')),
                    'appointment': ai_data.get('appointment')
                }
            except json.JSONDecodeError:
                # If JSON extraction fails, try extracting values directly
                priority = extract_priority_from_text(response_text)
                appointment = extract_date_from_text(response_text)
                return {
                    'priority': priority,
                    'appointment': appointment
                }
        else:
            # If no JSON found, try extracting values directly
            priority = extract_priority_from_text(response_text)
            appointment = extract_date_from_text(response_text)
            return {
                'priority': priority,
                'appointment': appointment
            }
    
    except requests.exceptions.RequestException as e:
        raise Exception(f"API request failed: {str(e)}")
    
    except Exception as e:
        raise Exception(f"Error processing AI recommendation: {str(e)}")

def validate_priority(priority):
    """Ensure priority is between 1-5"""
    try:
        priority = int(priority)
        return max(1, min(5, priority))
    except (ValueError, TypeError):
        return 1

def extract_priority_from_text(text):
    """Extract priority from raw text if JSON parsing fails"""
    match = re.search(r'priority[:\s]*([1-5])', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # Look for numeric values between 1-5
    match = re.search(r'\b([1-5])\b', text)
    return int(match.group(1)) if match else 1

def extract_date_from_text(text):
    """Extract date in YYYY-MM-DD format from text"""
    match = re.search(r'\d{4}-\d{2}-\d{2}', text)
    return match.group(0) if match else None

def calculate_priority_fallback(data):
    """Calculate priority based on patient data if AI fails"""
    priority = 1  # Default priority
    
    # Increase priority based on cancer stage
    try:
        stage = int(data['cancerStage'][0])  # Extract number from "Stage X"
        priority += min(stage - 1, 3)  # Stage 4 adds +3, Stage 1 adds +0
    except (ValueError, IndexError, TypeError):
        pass
    
    # Check vital signs
    try:
        # High temperature increases priority
        temp = float(data['temp'])
        if temp > 38.5:
            priority += 1
        
        # Abnormal heart rate increases priority
        heart = int(data['heart'])
        if heart > 100 or heart < 60:
            priority += 1
    except (ValueError, TypeError):
        pass
    
    # Check for emergency keywords in description
    emergency_keywords = ['severe', 'pain', 'emergency', 'urgent', 'bleeding', 
                          'unconscious', 'vomiting', 'difficulty breathing']
    
    if any(keyword in data['description'].lower() for keyword in emergency_keywords):
        priority += 1
    
    return min(priority, 5)  # Cap at 5

def calculate_appointment(priority, ai_date=None):
    """Determine appointment date based on priority and AI recommendation"""
    now = datetime.now()
    
    # Try to use AI-generated date if available and valid
    if ai_date:
        try:
            ai_datetime = datetime.strptime(ai_date, "%Y-%m-%d")
            
            # Validate the date isn't in the past
            if ai_datetime.date() >= now.date():
                # For high priority (4-5), ensure appointment is within 2 days
                if priority >= 4 and (ai_datetime.date() - now.date()).days > 2:
                    return now + timedelta(days=1)
                # For medium priority (3), ensure appointment is within 7 days
                elif priority == 3 and (ai_datetime.date() - now.date()).days > 7:
                    return now + timedelta(days=5)
                else:
                    return ai_datetime
        except ValueError:
            pass
    
    # Fallback calculation based on priority
    days_offset = {
        1: 14,  # Lowest priority (2 weeks)
        2: 10,  # Low priority
        3: 5,   # Medium priority
        4: 1,   # High priority (tomorrow)
        5: 0    # Highest priority (today)
    }.get(priority, 14)
    
    # Calculate appointment time
    appointment = now + timedelta(days=days_offset)
    
    # If it's high priority (4-5) and after hours (past 5 PM), schedule for next morning at 9 AM
    if priority >= 4 and now.hour >= 17:
        next_day = now.date() + timedelta(days=1)
        return datetime.combine(next_day, datetime.min.time()) + timedelta(hours=9)
    
    return appointment