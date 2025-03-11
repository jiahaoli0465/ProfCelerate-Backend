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
    """Save file data to a temporary file and return its path.
    
    Handles both file objects (with filename attribute) and 
    raw text content (string) for text files.
    """
    try:
        temp_dir = tempfile.gettempdir()
        
        # Check if file_data is a string (text content) or a file object
        if isinstance(file_data, str):
            # For text content, create a temporary file with .txt extension
            fd, temp_path = tempfile.mkstemp(suffix='.txt', dir=temp_dir)
            with os.fdopen(fd, 'w') as f:
                f.write(file_data)
            print(f"Saved string content to temporary file: {temp_path}")
            return temp_path
        
        # Check if file_data is a dictionary (might be from JSON)
        elif isinstance(file_data, dict):
            # Convert dict to JSON string and save as .txt
            fd, temp_path = tempfile.mkstemp(suffix='.txt', dir=temp_dir)
            with os.fdopen(fd, 'w') as f:
                json.dump(file_data, f, indent=2)
            print(f"Saved dictionary content to temporary file: {temp_path}")
            return temp_path
        
        # Check if file_data has the expected attributes of a file object
        elif hasattr(file_data, 'filename') and hasattr(file_data, 'save'):
            # Handle file object with filename attribute
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
            
            print(f"Saved file object to temporary file: {temp_path}")
            return temp_path
        
        # Handle bytes or bytearray
        elif isinstance(file_data, (bytes, bytearray)):
            # For binary content, create a temporary file
            fd, temp_path = tempfile.mkstemp(suffix='.bin', dir=temp_dir)
            with os.fdopen(fd, 'wb') as f:
                f.write(file_data)
            print(f"Saved binary content to temporary file: {temp_path}")
            return temp_path
        
        else:
            # Unsupported file_data type
            raise TypeError(f"Unsupported file data type: {type(file_data)}. Expected string, file object, dictionary, or bytes.")
            
    except Exception as e:
        print(f"Error saving temporary file: {str(e)}")
        print(f"Type of file_data: {type(file_data)}")
        if hasattr(file_data, '__dict__'):
            print(f"File data attributes: {file_data.__dict__}")
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

async def process_submission(files, grading_criteria, submission_id, total_points_available, supabase):
    """Process a batch of files for grading
    
    The files parameter can be:
    - A list of file objects (with filename attribute)
    - A list of strings (text content)
    - A dictionary of file objects
    """
    try:
        print(f"Number of files received: {len(files) if files else 0}")
        print(f"Type of files parameter: {type(files)}")
        
        # Save files to temp directory
        file_paths = []
        
        # Handle different types of file inputs
        if isinstance(files, dict):
            # Handle dictionary of files
            for _, file_obj in files.items():
                file_path = await save_temp_file(file_obj)
                file_paths.append(file_path)
        elif isinstance(files, list):
            # Handle list of files or strings
            for file_item in files:
                file_path = await save_temp_file(file_item)
                file_paths.append(file_path)
        else:
            # Single file or string
            file_path = await save_temp_file(files)
            file_paths.append(file_path)
        
        if not file_paths:
            raise ValueError("No valid files were processed")
            
        print(f"Successfully saved {len(file_paths)} files for processing")
        
        # Process PDFs and text files
        pdf_contents = {}
        text_contents = {}
        
        # Separate PDF and text files
        pdf_files = [f for f in file_paths if f.endswith('.pdf')]
        text_files = [f for f in file_paths if not f.endswith('.pdf')]
        
        # Process PDFs if any
        if pdf_files:
            try:
                for pdf_file in pdf_files:
                    try:
                        pdf_content = await process_pdf_with_mistral(pdf_file)
                        pdf_contents[os.path.basename(pdf_file)] = pdf_content
                    except Exception as e:
                        print(f"Error processing PDF {pdf_file}: {str(e)}")
                        continue
            except Exception as e:
                print(f"Error in PDF batch processing: {str(e)}")
        
        # Process text files if any
        if text_files:
            for text_file in text_files:
                try:
                    with open(text_file, 'r', encoding='utf-8') as f:
                        text_content = f.read()
                    # Process with Mistral if needed
                    # processed_text = await process_with_mistral(text_content)
                    # For now, just use the raw text
                    text_contents[os.path.basename(text_file)] = text_content
                except Exception as e:
                    print(f"Error processing text file {text_file}: {str(e)}")
                    continue

        # Combine all processed contents
        all_contents = {**pdf_contents, **text_contents}
        if not all_contents:
            raise ValueError("No content could be extracted from any files")

        # try:
        #     processed_contents = await mistral_processor.process_texts_batch(all_contents)
        # except Exception as e:
        #     print(f"Error in batch text processing: {str(e)}")
        #     processed_contents = all_contents  # Use original content if processing fails
        processed_contents = all_contents

        # Helper function to grade and store a single file
        async def grade_and_store(file_name, content):
            start_time = datetime.now()
            try:
                print(f"Starting grading for: {file_name}")
                # Grade the content
                grade_start = datetime.now()
                grading_result = await grade_with_deepseek(
                    content,
                    grading_criteria,
                    total_points_available
                )
                grade_end = datetime.now()
                grade_duration = (grade_end - grade_start).total_seconds()
                print(f"Grading for {file_name} completed in {grade_duration:.2f} seconds")
                
                # Get original file content for storage
                try:
                    # Try to find the exact file path
                    matching_files = [f for f in file_paths if os.path.basename(f) == file_name]
                    
                    if matching_files:
                        original_file_path = matching_files[0]
                    else:
                        # If no exact match, try case-insensitive match
                        file_name_lower = file_name.lower()
                        matching_files = [f for f in file_paths if os.path.basename(f).lower() == file_name_lower]
                        
                        if matching_files:
                            original_file_path = matching_files[0]
                        else:
                            # If still no match, log error and use a placeholder
                            print(f"Warning: Could not find original file for {file_name}")
                            # Create a placeholder file content
                            file_content = f"data:text/plain;base64,{base64.b64encode(content.encode('utf-8')).decode('utf-8')}"
                            
                            # Store the result with the placeholder content
                            store_start = datetime.now()
                            await store_grading_result(
                                supabase,
                                submission_id,
                                file_name,
                                file_content,
                                grading_result
                            )
                            store_end = datetime.now()
                            store_duration = (store_end - store_start).total_seconds()
                            print(f"Storing results for {file_name} completed in {store_duration:.2f} seconds")
                            
                            end_time = datetime.now()
                            total_duration = (end_time - start_time).total_seconds()
                            print(f"Total processing for {file_name} completed in {total_duration:.2f} seconds")
                            
                            return {
                                "fileName": file_name,
                                **grading_result
                            }
                    
                    # Read the file content
                    with open(original_file_path, 'rb') as file:
                        file_bytes = file.read()
                        mime_type = 'application/pdf' if file_name.endswith('.pdf') else 'text/plain'
                        file_content = f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('utf-8')}"
                
                except Exception as file_error:
                    print(f"Error reading original file for {file_name}: {str(file_error)}")
                    # Create a placeholder file content
                    file_content = f"data:text/plain;base64,{base64.b64encode(content.encode('utf-8')).decode('utf-8')}"

                # Store the result
                store_start = datetime.now()
                await store_grading_result(
                    supabase,
                    submission_id,
                    file_name,
                    file_content,
                    grading_result
                )
                store_end = datetime.now()
                store_duration = (store_end - store_start).total_seconds()
                print(f"Storing results for {file_name} completed in {store_duration:.2f} seconds")
                
                end_time = datetime.now()
                total_duration = (end_time - start_time).total_seconds()
                print(f"Total processing for {file_name} completed in {total_duration:.2f} seconds")
                
                return {
                    "fileName": file_name,
                    **grading_result
                }
            except Exception as e:
                end_time = datetime.now()
                total_duration = (end_time - start_time).total_seconds()
                print(f"Error processing {file_name} after {total_duration:.2f} seconds: {str(e)}")
                return {
                    "fileName": file_name,
                    "error": str(e)
                }

        # Create grading tasks for all files
        print(f"Creating {len(processed_contents)} grading tasks for concurrent processing")
        grading_tasks = []
        for file_name, content in processed_contents.items():
            # We don't call the coroutine here, just reference it to create a task
            # This is the key difference - we're not awaiting it yet
            task = grade_and_store(file_name, content)
            grading_tasks.append(task)
        
        # Run all grading tasks concurrently
        print(f"Running {len(grading_tasks)} grading tasks concurrently")
        start_time = datetime.now()
        results = await asyncio.gather(*grading_tasks, return_exceptions=True)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        print(f"Completed concurrent grading in {duration:.2f} seconds")
        
        # Process results and handle any exceptions
        final_results = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Error in concurrent processing: {str(result)}")
            else:
                final_results.append(result)
        
        # Clean up temp files
        for file_path in file_paths:
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error removing temp file {file_path}: {str(e)}")
        
        return final_results
    except Exception as e:
        print(f"Error in submission processing: {str(e)}")
        raise e 