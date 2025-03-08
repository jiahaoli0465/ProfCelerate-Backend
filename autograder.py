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

async def save_temp_file(file_data):
    """Save file data to a temporary file and return its path."""
    try:
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
        await file_data.save(temp_path)
        
        # Verify file was saved and is not empty
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise ValueError(f"Failed to save file or file is empty: {original_filename}")
            
        return temp_path
    except Exception as e:
        print(f"Error saving temporary file: {str(e)}")
        raise

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
        
        # Insert data into Supabase (don't await this operation)
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
        print(f"Starting to grade file: {file_path}")
        # Get original file name and content
        file_name = os.path.basename(file_path)
        
        # Read file content in binary mode to preserve file integrity
        with open(file_path, 'rb') as file:
            file_bytes = file.read()
            if len(file_bytes) == 0:
                raise ValueError(f"File {file_name} is empty")
                
            # Determine MIME type based on file extension
            mime_type = 'application/pdf' if file_path.endswith('.pdf') else 'text/plain'
            # Create proper base64 data URL
            file_content = f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('utf-8')}"
            print(f"Successfully read file {file_name} ({len(file_bytes)} bytes)")

        # Extract content based on file type
        if file_path.endswith('.pdf'):
            print(f"Processing PDF file: {file_name}")
            # Process PDF using Mistral's OCR and document understanding
            content = await process_pdf_with_mistral(file_path)
            print(f"Successfully extracted content from PDF: {file_name}")
        else:
            print(f"Processing text file: {file_name}")
            # For non-PDF files, read and process the content with Mistral
            with open(file_path, 'r', encoding='utf-8') as file:
                raw_content = file.read()
                content = await process_with_mistral(raw_content)
            print(f"Successfully processed text content from: {file_name}")

        # Grade the content using DeepSeek
        print(f"Starting grading for file: {file_name}")
        grading_result = await grade_with_deepseek(
            content,
            grading_criteria,
            total_points_available
        )
        print(f"Completed grading for file: {file_name}")

        # Store the result in Supabase
        try:
            print(f"Storing results for file: {file_name}")
            await store_grading_result(
                supabase,
                submission_id,
                file_name,
                file_content,
                grading_result
            )
            print(f"Successfully stored results for: {file_name}")
        except Exception as e:
            print(f"Error storing result in Supabase for {file_name}: {str(e)}")
            # Continue even if storage fails

        # Return the grading result
        result = {
            "fileName": file_name,
            **grading_result
        }
        print(f"Returning results for file: {file_name}")
        return result

    except Exception as e:
        print(f"Error processing file {os.path.basename(file_path)}: {str(e)}")
        # Return a structured error result
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
    """Process multiple files in a submission using batch processing."""
    temp_files = []  # Keep track of temporary files for cleanup
    try:
        # Save files first
        file_paths = []
        print(f"Starting to process {len(files)} files")
        for file in files.values():
            if file.filename:
                try:
                    temp_path = await save_temp_file(file)
                    temp_files.append(temp_path)
                    file_paths.append(temp_path)
                    print(f"Successfully saved file {file.filename} to {temp_path}")
                except Exception as e:
                    print(f"Error saving file {file.filename}: {str(e)}")
                    continue

        if not file_paths:
            raise ValueError("No valid files were saved for processing")

        print(f"Processing {len(file_paths)} files in batch")
        
        # Separate PDF and text files
        pdf_files = [f for f in file_paths if f.endswith('.pdf')]
        text_files = [f for f in file_paths if not f.endswith('.pdf')]
        
        # Process PDFs in batch
        pdf_contents = {}
        if pdf_files:
            try:
                pdf_contents = await mistral_processor.process_pdfs_batch(pdf_files)
            except Exception as e:
                print(f"Error in batch PDF processing: {str(e)}")
                # Fallback to sequential processing
                for pdf_file in pdf_files:
                    try:
                        print(f"Processing {pdf_file} sequentially")
                        content = await mistral_processor.process_pdf(pdf_file)
                        pdf_contents[os.path.basename(pdf_file)] = content
                    except Exception as seq_error:
                        print(f"Sequential processing failed for {pdf_file}, falling back to PyPDF2: {str(seq_error)}")
                        try:
                            text_content = ""
                            with open(pdf_file, 'rb') as file:
                                pdf_reader = PyPDF2.PdfReader(file)
                                for page in pdf_reader.pages:
                                    text_content += page.extract_text() + "\n"
                            pdf_contents[os.path.basename(pdf_file)] = text_content
                        except Exception as fallback_error:
                            print(f"Fallback extraction failed for {pdf_file}: {str(fallback_error)}")
                            pdf_contents[os.path.basename(pdf_file)] = "Failed to extract content from PDF."

        # Process text files sequentially if batch fails
        text_contents = {}
        if text_files:
            for text_file in text_files:
                try:
                    with open(text_file, 'r', encoding='utf-8') as file:
                        raw_content = file.read()
                        processed_content = await mistral_processor.process_text(raw_content)
                        text_contents[os.path.basename(text_file)] = processed_content
                except Exception as e:
                    print(f"Error processing text file {text_file}: {str(e)}")
                    continue

        # Combine all processed contents
        all_contents = {**pdf_contents, **text_contents}
        if not all_contents:
            raise ValueError("No content could be extracted from any files")

        try:
            processed_contents = await mistral_processor.process_texts_batch(all_contents)
        except Exception as e:
            print(f"Error in batch text processing: {str(e)}")
            processed_contents = all_contents  # Use original content if processing fails

        # Grade all processed content and store results
        results = []
        for file_name, content in processed_contents.items():
            try:
                print(f"Grading content for: {file_name}")
                # Grade the content
                grading_result = await grade_with_deepseek(
                    content,
                    grading_criteria,
                    total_points_available
                )
                
                # Get original file content for storage
                original_file_path = next(f for f in file_paths if os.path.basename(f) == file_name)
                with open(original_file_path, 'rb') as file:
                    file_bytes = file.read()
                    mime_type = 'application/pdf' if file_name.endswith('.pdf') else 'text/plain'
                    file_content = f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('utf-8')}"

                # Store the result
                try:
                    await store_grading_result(
                        supabase,
                        submission_id,
                        file_name,
                        file_content,
                        grading_result
                    )
                except Exception as e:
                    print(f"Error storing result for {file_name}: {str(e)}")

                # Add to results
                results.append({
                    "fileName": file_name,
                    **grading_result
                })
                print(f"Successfully processed {file_name}")
            except Exception as e:
                print(f"Error processing {file_name}: {str(e)}")
                results.append({
                    "fileName": file_name,
                    "results": [{
                        "question": "Error in processing",
                        "mistakes": ["File processing failed"],
                        "score": 0,
                        "feedback": f"Error: {str(e)}"
                    }],
                    "totalScore": 0,
                    "overallFeedback": f"An error occurred during processing: {str(e)}"
                })

        if not results:
            raise Exception("No files were successfully processed")

        return results

    except Exception as e:
        print(f"Error in process_submission: {str(e)}")
        raise

    finally:
        # Clean up temporary files
        for temp_path in temp_files:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    print(f"Cleaned up temporary file: {temp_path}")
            except Exception as e:
                print(f"Error cleaning up temporary file {temp_path}: {str(e)}") 