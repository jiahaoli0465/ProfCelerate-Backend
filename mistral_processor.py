import os
import json
import asyncio
from mistralai import Mistral
from dotenv import load_dotenv
from typing import List, Dict, Any

class MistralProcessor:
    def __init__(self):
        """Initialize the Mistral processor with API credentials."""
        load_dotenv()
        self.api_key = os.getenv('MISTRAL_API_KEY')
        if not self.api_key:
            raise ValueError("Missing MISTRAL_API_KEY environment variable")
            
        print(f"Initializing Mistral client with API key starting with: {self.api_key[:4]}...")
        self.client = Mistral(api_key=self.api_key)

    async def process_pdfs_batch(self, file_paths: List[str]) -> Dict[str, str]:
        """Process multiple PDFs using Mistral's batch API."""
        try:
            print(f"Processing {len(file_paths)} PDFs in batch...")
            
            # Create batch requests for each file
            batch_requests = []
            for idx, file_path in enumerate(file_paths):
                with open(file_path, "rb") as file:
                    # Upload each file for OCR
                    uploaded_file = await self.client.files.upload_async(
                        file={
                            "file_name": os.path.basename(file_path),
                            "content": file,
                        },
                        purpose="ocr"
                    )
                    
                    # Get signed URL
                    signed_url = await self.client.files.get_signed_url_async(file_id=uploaded_file.id)
                    
                    # Create batch request for this file
                    batch_requests.append({
                        "custom_id": str(idx),
                        "body": {
                            "model": "mistral-ocr-latest",
                            "document": {
                                "type": "document_url",
                                "document_url": signed_url.url,
                            }
                        }
                    })

            # Create batch file
            batch_file_content = "\n".join([json.dumps(req) for req in batch_requests])
            
            # Upload batch file
            batch_data = self.client.files.upload(
                file={
                    "file_name": "batch_ocr.jsonl",
                    "content": batch_file_content.encode()
                },
                purpose="batch"
            )

            # Create and start batch job
            job = self.client.batch.jobs.create(
                input_files=[batch_data.id],
                model="mistral-ocr-latest",
                endpoint="/v1/ocr",
                metadata={"job_type": "pdf_ocr"}
            )

            print(f"Started batch job {job.id}")

            # Poll for results
            while True:
                job_status = self.client.batch.jobs.get(job_id=job.id)
                if job_status.status == "SUCCESS":
                    results = self.client.files.download(file_id=job_status.output_file)
                    break
                elif job_status.status in ["FAILED", "TIMEOUT_EXCEEDED", "CANCELLED"]:
                    raise Exception(f"Batch job failed with status: {job_status.status}")
                await asyncio.sleep(1)  # Poll interval

            # Process results
            results_dict = {}
            for line in results.splitlines():
                result = json.loads(line)
                file_idx = result["custom_id"]
                file_path = file_paths[int(file_idx)]
                file_name = os.path.basename(file_path)
                
                # Extract text from OCR response
                ocr_text = ""
                for page in result["response"]["pages"]:
                    if "markdown" in page:
                        ocr_text += page["markdown"] + "\n\n"
                    elif "text" in page:
                        ocr_text += page["text"] + "\n\n"
                
                results_dict[file_name] = ocr_text.strip()

            print(f"Successfully processed {len(results_dict)} files in batch")
            return results_dict

        except Exception as e:
            print(f"Error in batch processing: {str(e)}")
            raise

    async def process_texts_batch(self, texts: Dict[str, str]) -> Dict[str, str]:
        """Process multiple text contents with Mistral AI in batch."""
        try:
            print(f"Processing {len(texts)} texts in batch...")
            
            # Create batch requests
            batch_requests = []
            for idx, (file_name, content) in enumerate(texts.items()):
                batch_requests.append({
                    "custom_id": str(idx),
                    "body": {
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert at understanding and analyzing text content. Please process the following text to extract key information, maintain structure, and improve clarity."
                            },
                            {
                                "role": "user",
                                "content": content
                            }
                        ]
                    }
                })

            # Create batch file
            batch_file_content = "\n".join([json.dumps(req) for req in batch_requests])
            
            # Upload batch file
            batch_data = self.client.files.upload(
                file={
                    "file_name": "batch_text.jsonl",
                    "content": batch_file_content.encode()
                },
                purpose="batch"
            )

            # Create and start batch job
            job = self.client.batch.jobs.create(
                input_files=[batch_data.id],
                model="mistral-large-latest",
                endpoint="/v1/chat/completions",
                metadata={"job_type": "text_processing"}
            )

            print(f"Started batch job {job.id}")

            # Poll for results
            while True:
                job_status = self.client.batch.jobs.get(job_id=job.id)
                if job_status.status == "SUCCESS":
                    results = self.client.files.download(file_id=job_status.output_file)
                    break
                elif job_status.status in ["FAILED", "TIMEOUT_EXCEEDED", "CANCELLED"]:
                    raise Exception(f"Batch job failed with status: {job_status.status}")
                await asyncio.sleep(1)  # Poll interval

            # Process results
            results_dict = {}
            file_names = list(texts.keys())
            for line in results.splitlines():
                result = json.loads(line)
                file_idx = int(result["custom_id"])
                file_name = file_names[file_idx]
                results_dict[file_name] = result["response"]["choices"][0]["message"]["content"]

            print(f"Successfully processed {len(results_dict)} texts in batch")
            return results_dict

        except Exception as e:
            print(f"Error in batch text processing: {str(e)}")
            raise

    # Keep the old methods for backward compatibility and single-file processing
    async def process_pdf(self, file_path: str) -> str:
        """Process a single PDF using batch processing."""
        results = await self.process_pdfs_batch([file_path])
        return results[os.path.basename(file_path)]

    async def process_text(self, text_content: str) -> str:
        """Process a single text using batch processing."""
        results = await self.process_texts_batch({"text": text_content})
        return results["text"]

    async def process_pdf_content(self, text_content: str) -> str:
        """Process PDF text content with Mistral AI."""
        if not text_content.strip():
            return "No text content could be extracted from the PDF."
        
        return await self.process_text(text_content) 