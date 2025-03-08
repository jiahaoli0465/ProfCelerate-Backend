from quart import Quart, Response, request
from quart_cors import cors
import json
import os
import tempfile
from werkzeug.utils import secure_filename
import asyncio
from supabase import create_client, Client
from typing import Optional, Dict, Any, List, Tuple
from autograder import grade_file
from dotenv import load_dotenv

# Initialize app
app = Quart(__name__)
app = cors(app, allow_origin="*")


load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.")

# Initialize Supabase client
print(f"Connecting to Supabase URL: {SUPABASE_URL}")
print(f"Using service role key starting with: {SUPABASE_KEY[:6]}...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def create_json_response(data: Dict[str, Any], status_code: int = 200) -> Response:
    """Helper function to create JSON responses with proper headers."""
    return Response(
        json.dumps(data),
        status=status_code,
        mimetype='application/json'
    )

# Test endpoint
@app.route('/api/test', methods=['GET'])
async def test():
    """Test endpoint to verify the backend is running."""
    return create_json_response({"message": "Backend is running successfully!"})

# Get user profile endpoint
@app.route('/api/profile/<user_id>', methods=['GET'])
async def get_profile(user_id):
    """Get or create a user profile."""
    try:
        if user_id == 'undefined' or not user_id:
            return create_json_response({
                "error": "Validation error",
                "message": "Invalid user ID provided",
                "details": {"user_id": user_id}
            }, 400)
        
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
                return create_json_response({
                    "success": True,
                    "data": create_response.data[0],
                    "message": "New profile created successfully"
                })
            return create_json_response({
                "error": "Database error",
                "message": "Failed to create profile",
                "details": create_response.error if hasattr(create_response, 'error') else None
            }, 500)
            
        return create_json_response({
            "success": True,
            "data": response.data[0],
            "message": "Profile retrieved successfully"
        })
    except Exception as e:
        print(f"Error in get_profile: {str(e)}")
        return create_json_response({
            "error": "Server error",
            "message": "Failed to process profile request",
            "details": str(e)
        }, 500)

# Simple file saving function
async def save_file_to_temp(file) -> str:
    """Save a file to a temporary location and return the path."""
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"temp_{secure_filename(file.filename)}")
    await file.save(temp_path)
    return temp_path

# Autograder endpoint
@app.route('/api/grade', methods=['POST'])
async def grade_submission():
    """Handle file submission grading requests."""
    try:
        # Extract form data
        form = await request.form
        files = await request.files
        
        # Convert to dictionaries for easier handling
        form_data = dict(form)
        files_dict = dict(files)
        
        print(f"Received form data: {form_data}")
        print(f"Received files: {[f.filename for f in files_dict.values()]}")
        
        # Basic validation
        if not files_dict:
            return create_json_response({
                "error": "Validation error",
                "message": "No files provided",
                "details": "Request must include files"
            }, 400)
            
        if 'gradingCriteria' not in form_data:
            return create_json_response({
                "error": "Validation error",
                "message": "Missing grading criteria",
                "details": "gradingCriteria field is required"
            }, 400)
            
        if 'submissionId' not in form_data:
            return create_json_response({
                "error": "Validation error",
                "message": "Missing submission ID",
                "details": "submissionId field is required"
            }, 400)
        
        # Extract validated data
        grading_criteria = form_data['gradingCriteria']
        submission_id = form_data['submissionId']
        
        try:
            total_points = float(form_data.get('totalPointsAvailable', 100))
        except ValueError:
            total_points = 100
            
        # Update submission status to grading
        try:
            supabase.from_('submissions').update(
                {'status': 'grading'}
            ).eq('id', submission_id).execute()
        except Exception as e:
            print(f"Error updating submission status: {str(e)}")
        
        # Process files one by one
        results = []
        errors = []
        
        for file_key, file in files_dict.items():
            if not file.filename:
                continue
                
            temp_path = None
            try:
                # Save file to temp location
                temp_path = await save_file_to_temp(file)
                
                # Grade the file
                result = await grade_file(
                    temp_path,
                    grading_criteria,
                    submission_id,
                    total_points,
                    supabase
                )
                
                if result:
                    results.append(result)
                    
            except Exception as e:
                print(f"Error processing file {file.filename}: {str(e)}")
                errors.append({
                    "file": file.filename,
                    "error": str(e)
                })
            finally:
                # Clean up temp file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as e:
                        print(f"Error removing temp file: {str(e)}")
        
        # Update submission status based on results
        status = 'completed'
        if not results:
            status = 'failed'
        elif errors:
            status = 'partial'
            
        try:
            supabase.from_('submissions').update(
                {'status': status}
            ).eq('id', submission_id).execute()
        except Exception as e:
            print(f"Error updating submission status: {str(e)}")
        
        # Return response
        if not results and errors:
            return create_json_response({
                "error": "Processing error",
                "message": "All files failed processing",
                "details": errors
            }, 500)
            
        return create_json_response({
            "success": True,
            "data": results,
            "errors": errors if errors else None,
            "status": status,
            "message": f"Grading completed with status: {status}"
        })
        
    except Exception as e:
        print(f"Unexpected error in grade_submission: {str(e)}")
        return create_json_response({
            "error": "Server error",
            "message": "An unexpected error occurred",
            "details": str(e)
        }, 500)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True) 