from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import os
from quart import Quart
from quart_cors import cors
from autograder import process_submission
from functools import wraps
import time
from typing import Dict, Any, Optional

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Missing Supabase credentials. Please check your .env file.")

print(f"Connecting to Supabase URL: {supabase_url}")
print(f"Using service role key starting with: {supabase_key[:6]}...")

supabase: Client = create_client(supabase_url, supabase_key)

# Initialize Quart app (async version of Flask)
app = Quart(__name__)
app = cors(app)

# Rate limiting configuration
RATE_LIMIT_WINDOW = 60  # 60 seconds
MAX_REQUESTS = 10  # Maximum requests per window
rate_limit_data: Dict[str, Dict[str, Any]] = {}

def validate_grading_request(files, form) -> Optional[tuple]:
    """
    Validate the grading request parameters.
    Returns None if valid, or a tuple of (error_message, status_code) if invalid.
    """
    if not files:
        return "No files provided", 400

    if not form.get('gradingCriteria'):
        return "No grading criteria provided", 400

    if not form.get('submissionId'):
        return "No submission ID provided", 400

    try:
        total_points = float(form.get('totalPointsAvailable', 100))
        if total_points <= 0:
            return "Total points available must be greater than 0", 400
    except ValueError:
        return "Invalid total points value", 400

    return None

def rate_limit(f):
    """
    Rate limiting decorator for API endpoints.
    Limits requests based on IP address.
    """
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        # Get client IP
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        current_time = time.time()

        # Initialize or clean up rate limit data for this IP
        if ip not in rate_limit_data:
            rate_limit_data[ip] = {
                'requests': [],
                'blocked_until': None
            }

        # Clean up old requests
        rate_limit_data[ip]['requests'] = [
            req_time for req_time in rate_limit_data[ip]['requests']
            if current_time - req_time < RATE_LIMIT_WINDOW
        ]

        # Check if client is blocked
        if rate_limit_data[ip].get('blocked_until'):
            if current_time < rate_limit_data[ip]['blocked_until']:
                wait_time = int(rate_limit_data[ip]['blocked_until'] - current_time)
                return jsonify({
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Please try again in {wait_time} seconds.",
                    "wait_time": wait_time
                }), 429
            else:
                rate_limit_data[ip]['blocked_until'] = None

        # Check rate limit
        if len(rate_limit_data[ip]['requests']) >= MAX_REQUESTS:
            rate_limit_data[ip]['blocked_until'] = current_time + RATE_LIMIT_WINDOW
            return jsonify({
                "error": "Rate limit exceeded",
                "message": f"Too many requests. Please try again in {RATE_LIMIT_WINDOW} seconds.",
                "wait_time": RATE_LIMIT_WINDOW
            }), 429

        # Add current request timestamp
        rate_limit_data[ip]['requests'].append(current_time)

        return await f(*args, **kwargs)
    return decorated_function

# Autograder endpoint
@app.route('/api/grade', methods=['POST'])
@rate_limit
async def grade_submission():
    try:
        files = await request.files
        form = await request.form

        # Validate request
        validation_error = validate_grading_request(files, form)
        if validation_error:
            error_msg, status_code = validation_error
            return jsonify({
                "error": "Validation error",
                "message": error_msg,
                "details": {
                    "files_present": bool(files),
                    "grading_criteria_present": bool(form.get('gradingCriteria')),
                    "submission_id_present": bool(form.get('submissionId')),
                    "total_points_valid": bool(form.get('totalPointsAvailable', '100').replace('.', '').isdigit())
                }
            }), status_code

        grading_criteria = form.get('gradingCriteria')
        submission_id = form.get('submissionId')
        total_points_available = float(form.get('totalPointsAvailable', 100))

        # Update submission status to grading
        try:
            supabase.from_('submissions').update(
                {'status': 'grading'}
            ).eq('id', submission_id).execute()
        except Exception as e:
            return jsonify({
                "error": "Database error",
                "message": "Failed to update submission status",
                "details": str(e)
            }), 500

        try:
            results = await process_submission(
                files,
                grading_criteria,
                submission_id,
                total_points_available,
                supabase
            )
            return jsonify({
                "success": True,
                "data": results,
                "message": "Grading completed successfully"
            })
        except Exception as e:
            # Ensure submission status is updated to failed on error
            supabase.from_('submissions').update(
                {'status': 'failed'}
            ).eq('id', submission_id).execute()
            
            return jsonify({
                "error": "Grading error",
                "message": "Failed to process submission",
                "details": str(e),
                "submission_id": submission_id
            }), 500

    except Exception as e:
        return jsonify({
            "error": "Server error",
            "message": "An unexpected error occurred",
            "details": str(e)
        }), 500

# Test endpoint
@app.route('/api/test', methods=['GET'])
@rate_limit
async def test():
    return jsonify({"message": "Backend is running successfully!"})

# Get user profile endpoint
@app.route('/api/profile/<user_id>', methods=['GET'])
@rate_limit
async def get_profile(user_id):
    try:
        if user_id == 'undefined' or not user_id:
            return jsonify({
                "error": "Validation error",
                "message": "Invalid user ID provided",
                "details": {"user_id": user_id}
            }), 400
        
        response = supabase.from_('profiles').select('*').eq('user_id', user_id).execute()
        
        if not response.data or len(response.data) == 0:
            new_profile = {
                'user_id': user_id,
                'full_name': '',
                'institution': '',
                'department': '',
            }
            create_response = supabase.from_('profiles').insert(new_profile).execute()
            if create_response.data:
                return jsonify({
                    "success": True,
                    "data": create_response.data[0],
                    "message": "New profile created successfully"
                })
            return jsonify({
                "error": "Database error",
                "message": "Failed to create profile",
                "details": create_response.error if hasattr(create_response, 'error') else None
            }), 500
            
        return jsonify({
            "success": True,
            "data": response.data[0],
            "message": "Profile retrieved successfully"
        })
    except Exception as e:
        return jsonify({
            "error": "Server error",
            "message": "Failed to process profile request",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 