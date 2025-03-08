import os
import json
import asyncio
import tempfile
import PyPDF2
import base64
from datetime import datetime
from werkzeug.utils import secure_filename
from mistral_processor import MistralProcessor
from deepseek_grader import DeepSeekGrader

# Initialize processors
mistral_processor = MistralProcessor()
deepseek_grader = DeepSeekGrader()

def save_temp_file(file_data):
    """Save file data to a temporary file and return its path."""
    temp_dir = tempfile.gettempdir()
    # Get original filename but ensure it's secure
    original_filename = secure_filename(file_data.filename)
    # Generate a unique filename while preserving the original name
    temp_path = os.path.join(temp_dir, original_filename)
    # If file exists, add a number to make it unique
    counter = 1
    while os.path.exists(temp_path):
        name, ext = os.path.splitext(original_filename)
        temp_path = os.path.join(temp_dir, f"{name}_{counter}{ext}")
        counter += 1
    
    # Save the file in binary mode to preserve file integrity
    with open(temp_path, 'wb') as f:
        file_data.save(f)
    return temp_path

async def process_pdf_with_mistral(file_path):
    """Process PDF using Mistral's OCR and language capabilities."""
    try:
        # Use Mistral's OCR and document understanding
        return await mistral_processor.process_pdf(file_path)
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        # Fallback to PyPDF2 if Mistral OCR fails
        try:
            print("Falling back to PyPDF2 for text extraction...")
            text_content = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text_content += page.extract_text() + "\n"
            
            return await mistral_processor.process_pdf_content(text_content)
        except Exception as fallback_error:
            print(f"Fallback text extraction failed: {str(fallback_error)}")
            return "Failed to extract content from PDF."

async def process_with_mistral(text_content):
    """Process text content with Mistral AI."""
    return await mistral_processor.process_text(text_content)

async def grade_with_deepseek(content, grading_criteria, total_points_available):
    """Grade content using DeepSeek's API."""
    return await deepseek_grader.grade_submission(content, grading_criteria, float(total_points_available))

async def store_grading_result(supabase, submission_id, file_name, file_content, grading_result):
    """Store the grading result in Supabase."""
    try:
        # Prepare data for storage
        data = {
            "submission_id": submission_id,
            "file_name": file_name,
            "file_content": file_content,
            "grading_results": grading_result,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        # Insert data into Supabase
        response = supabase.from_('submission_results').insert(data).execute()
        
        # Check for errors
        if hasattr(response, 'error') and response.error:
            print(f"Supabase error: {response.error}")
            return None
            
        return response.data
    except Exception as e:
        print(f"Error storing grading result: {str(e)}")
        return None

async def grade_file(file_path, grading_criteria, submission_id, total_points_available, supabase):
    """Grade a single file using Mistral for content processing and DeepSeek for grading."""
    try:
        # Get original file name and content
        file_name = os.path.basename(file_path)
        
        # Read file content in binary mode to preserve file integrity
        with open(file_path, 'rb') as file:
            file_content = base64.b64encode(file.read()).decode('utf-8')

        # Extract content based on file type
        if file_path.endswith('.pdf'):
            # Process PDF using Mistral's OCR and document understanding
            content = await process_pdf_with_mistral(file_path)
            print('extracted content from pdf', content)
        else:
            # For non-PDF files, read and process the content with Mistral
            with open(file_path, 'r', encoding='utf-8') as file:
                raw_content = file.read()
                content = await process_with_mistral(raw_content)

        # Grade the content using DeepSeek
        grading_result = await grade_with_deepseek(
            content,
            grading_criteria,
            total_points_available
        )

        print('grading result', grading_result)

        # Store the result in Supabase
        try:
            await store_grading_result(
                supabase,
                submission_id,
                file_name,  # Use original filename
                file_content,
                grading_result
            )
        except Exception as e:
            print(f"Error storing result in Supabase: {str(e)}")
            # Continue even if storage fails

        # Return the grading result
        return {
            "fileName": file_name,  # Use original filename
            **grading_result
        }

    except Exception as e:
        print(f"Error in grade_file: {str(e)}")
        # Return a basic error result
        error_result = {
            "fileName": os.path.basename(file_path),
            "results": [
                {
                    "question": "Error in processing",
                    "mistakes": ["File processing failed"],
                    "score": 0,
                    "feedback": f"Error: {str(e)}"
                }
            ],
            "totalScore": 0,
            "overallFeedback": f"An error occurred during processing: {str(e)}"
        }
        return error_result

async def process_submission(files, grading_criteria, submission_id, total_points_available, supabase):
    """Process multiple files in a submission concurrently."""
    temp_files = []  # Keep track of temporary files for cleanup
    try:
        # Save files first
        file_paths = []
        for file in files.values():
            if file.filename:
                temp_path = save_temp_file(file)
                temp_files.append(temp_path)
                file_paths.append(temp_path)

        if not file_paths:
            raise ValueError("No valid files to process")

        # Create tasks for each file
        tasks = [
            grade_file(
                file_path,
                grading_criteria,
                submission_id,
                total_points_available,
                supabase
            )
            for file_path in file_paths
        ]

        # Process all files concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and handle exceptions
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Error in file processing: {str(result)}")
                continue
            if result is not None:
                valid_results.append(result)

        if not valid_results:
            raise Exception("No files were successfully processed")

        return valid_results

    except Exception as e:
        print(f"Error in process_submission: {str(e)}")
        raise

    finally:
        # Clean up temporary files
        for temp_path in temp_files:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                print(f"Error cleaning up temporary file {temp_path}: {str(e)}") 