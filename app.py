from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import os
from quart import Quart
from quart_cors import cors
from autograder import process_submission

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

# Autograder endpoint
@app.route('/api/grade', methods=['POST'])
async def grade_submission():
    try:
        files = await request.files
        if not files:
            return jsonify({"error": "No files provided"}), 400

        form = await request.form
        grading_criteria = form.get('gradingCriteria')
        submission_id = form.get('submissionId')
        total_points_available = float(form.get('totalPointsAvailable', 100))

        if not grading_criteria:
            return jsonify({"error": "No grading criteria provided"}), 400

        # Update submission status to grading
        supabase.from_('submissions').update(
            {'status': 'grading'}
        ).eq('id', submission_id).execute()

        try:
            results = await process_submission(
                files,
                grading_criteria,
                submission_id,
                total_points_available,
                supabase
            )
            return jsonify(results)
        except Exception as e:
            # Ensure submission status is updated to failed on error
            supabase.from_('submissions').update(
                {'status': 'failed'}
            ).eq('id', submission_id).execute()
            raise e

    except Exception as e:
        print(f"Error in grade_submission: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Test endpoint
@app.route('/api/test', methods=['GET'])
async def test():
    return jsonify({"message": "Backend is running successfully!"})

# Get user profile endpoint
@app.route('/api/profile/<user_id>', methods=['GET'])
async def get_profile(user_id):
    try:
        print(f"Fetching profile for user_id: {user_id}")
        
        if user_id == 'undefined' or not user_id:
            print(f"Invalid user_id received: {user_id}")
            return jsonify({"error": "Invalid user ID"}), 400
        
        response = supabase.from_('profiles').select('*').eq('user_id', user_id).execute()
        print(f"Response data: {response.data}")
        
        if not response.data or len(response.data) == 0:
            print(f"No profile found for user_id: {user_id}")
            new_profile = {
                'user_id': user_id,
                'full_name': '',
                'institution': '',
                'department': '',
            }
            create_response = supabase.from_('profiles').insert(new_profile).execute()
            if create_response.data:
                return jsonify(create_response.data[0])
            return jsonify({"error": "Failed to create profile"}), 500
            
        return jsonify(response.data[0])
    except Exception as e:
        print(f"Error in profile operation: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 