import os
import json
import asyncio
from openai import OpenAI
from werkzeug.utils import secure_filename
import tempfile
import PyPDF2
import base64
from datetime import datetime
from mistralai import Mistral

# Initialize clients
mistral_client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))
deepseek_client = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com"
)

def save_temp_file(file_data):
    """Save file data to a temporary file and return its path."""
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"temp_{secure_filename(file_data.filename)}")
    file_data.save(temp_path)
    return temp_path

async def process_pdf_with_mistral(file_path):
    """Process PDF using Mistral's document processing capabilities."""
    try:
        # Upload the file to Mistral
        with open(file_path, "rb") as file:
            uploaded_file = mistral_client.files.upload(
                file={
                    "file_name": os.path.basename(file_path),
                    "content": file,
                },
                purpose="ocr"
            )

        # Get signed URL for the uploaded file
        signed_url = mistral_client.files.get_signed_url(file_id=uploaded_file.id)

        try:
            # Process the document using OCR
            ocr_response = mistral_client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "document_url",
                    "document_url": signed_url.url,
                }
            )

            # Use document understanding to extract and organize content
            chat_response = mistral_client.chat.complete(
                model="mistral-large-latest",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Please extract and organize all the content from this document in a clear, well-structured format. Maintain all important information and improve readability."
                            },
                            {
                                "type": "document_url",
                                "document_url": signed_url.url
                            }
                        ]
                    }
                ]
            )

            # Combine OCR text and chat understanding
            content = f"{ocr_response.text}\n\n{chat_response.choices[0].message.content}"
            
            return content

        finally:
            # Clean up the uploaded file
            mistral_client.files.delete(file_id=uploaded_file.id)

    except Exception as e:
        print(f"Error processing PDF with Mistral: {str(e)}")
        # Fallback to PyPDF2 if Mistral processing fails
        try:
            text_content = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text_content += page.extract_text() + "\n"
            return text_content
        except Exception as e2:
            print(f"Fallback PDF extraction failed: {str(e2)}")
            raise

async def process_with_mistral(text_content):
    """Process text content with Mistral AI to improve understanding."""
    try:
        chat_response = mistral_client.chat.complete(
            model="mistral-large-latest",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at understanding and analyzing text content. Please process the following text to extract key information, maintain structure, and improve clarity."
                },
                {
                    "role": "user",
                    "content": text_content
                }
            ]
        )
        
        return chat_response.choices[0].message.content
    except Exception as e:
        print(f"Error processing with Mistral: {str(e)}")
        raise

async def grade_with_deepseek(content, grading_criteria, total_points_available):
    """Grade content using DeepSeek's API."""
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": """You are an expert grader. Grade the submission based on the provided criteria and return a JSON object in this exact format:
                {
                    "results": [
                        {
                            "question": "Question or aspect being graded",
                            "mistakes": ["List of specific mistakes found"],
                            "score": number,
                            "feedback": "Detailed, constructive feedback"
                        }
                    ],
                    "totalScore": number,
                    "overallFeedback": "Comprehensive overall feedback"
                }
                Be thorough in your grading and provide specific, actionable feedback."""},
                {"role": "user", "content": f"""Please grade this submission:

Grading Criteria:
{grading_criteria}

Total Points Available: {total_points_available}

Submission Content:
{content}"""}
            ],
            temperature=0.3,
            max_tokens=2000,
            stream=False
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Validate and ensure the grading result has the expected structure
        validated_result = {
            "results": [
                {
                    "question": r.get("question", "Unnamed aspect"),
                    "mistakes": r.get("mistakes", []) if isinstance(r.get("mistakes"), list) else [],
                    "score": float(r.get("score", 0)),
                    "feedback": r.get("feedback", "No feedback provided")
                }
                for r in result.get("results", [])
            ],
            "totalScore": float(result.get("totalScore", 0)),
            "overallFeedback": result.get("overallFeedback", "No overall feedback provided")
        }
        
        return validated_result
    except Exception as e:
        print(f"Error grading with DeepSeek: {str(e)}")
        raise

async def store_grading_result(supabase, submission_id, file_name, file_content, grading_result):
    """Store the grading result in Supabase."""
    try:
        data = {
            "submission_id": submission_id,
            "file_name": file_name,
            "file_content": file_content,
            "grading_results": grading_result,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        response = supabase.from_('submission_results').insert(data).execute()
        if hasattr(response, 'error') and response.error:
            raise Exception(f"Error storing result: {response.error}")
            
        return response.data
    except Exception as e:
        print(f"Error storing grading result: {str(e)}")
        raise

async def grade_file(file_path, grading_criteria, submission_id, total_points_available, supabase):
    """Grade a single file using Mistral for content processing and DeepSeek for grading."""
    try:
        # Get original file name and content
        file_name = os.path.basename(file_path)
        with open(file_path, 'rb') as file:
            file_content = base64.b64encode(file.read()).decode('utf-8') if file_path.endswith('.pdf') else file.read()

        # Extract content based on file type
        if file_path.endswith('.pdf'):
            # Process PDF using Mistral's document processing
            content = await process_pdf_with_mistral(file_path)
        else:
            # For non-PDF files, read and process the content
            with open(file_path, 'r') as file:
                raw_content = file.read()
                content = await process_with_mistral(raw_content)

        # Grade the content using DeepSeek
        grading_result = await grade_with_deepseek(
            content,
            grading_criteria,
            total_points_available
        )

        # Store the result in Supabase
        await store_grading_result(
            supabase,
            submission_id,
            file_name,
            file_content,
            grading_result
        )

        # Return the grading result
        return {
            "fileName": file_name,
            **grading_result
        }

    except Exception as e:
        print(f"Error in grade_file: {str(e)}")
        raise

async def process_submission(files, grading_criteria, submission_id, total_points_available, supabase):
    """Process multiple files in a submission concurrently."""
    try:
        async def process_single_file(file_key):
            file = files[file_key]
            if not file.filename:
                return None
                
            # Save file temporarily
            temp_path = save_temp_file(file)
            
            try:
                # Grade the file
                result = await grade_file(
                    temp_path,
                    grading_criteria,
                    submission_id,
                    total_points_available,
                    supabase
                )
                
                # Add filename to result
                result['fileName'] = file.filename
                return result
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        # Process all files concurrently
        grading_tasks = [
            process_single_file(file_key)
            for file_key in files
        ]
        
        # Wait for all grading tasks to complete
        results = await asyncio.gather(*grading_tasks, return_exceptions=True)
        
        # Filter out None results and handle any exceptions
        valid_results = []
        has_errors = False
        
        for result in results:
            if isinstance(result, Exception):
                print(f"Error processing file: {str(result)}")
                has_errors = True
            elif result is not None:
                valid_results.append(result)

        # Update submission status based on results
        if has_errors:
            supabase.from_('submissions').update(
                {'status': 'failed'}
            ).eq('id', submission_id).execute()
            if not valid_results:  # If no successful results, raise the error
                raise Exception("All file processing failed")
        else:
            supabase.from_('submissions').update(
                {'status': 'completed'}
            ).eq('id', submission_id).execute()

        return valid_results

    except Exception as e:
        print(f"Error in process_submission: {str(e)}")
        # Update submission status to failed
        supabase.from_('submissions').update(
            {'status': 'failed'}
        ).eq('id', submission_id).execute()
        raise 