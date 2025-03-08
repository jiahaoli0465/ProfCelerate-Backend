import os
from mistralai import Mistral
from dotenv import load_dotenv

class MistralProcessor:
    def __init__(self):
        """Initialize the Mistral processor with API credentials."""
        load_dotenv()
        self.api_key = os.getenv('MISTRAL_API_KEY')
        if not self.api_key:
            raise ValueError("Missing MISTRAL_API_KEY environment variable")
            
        print(f"Initializing Mistral client with API key starting with: {self.api_key[:4]}...")
        self.client = Mistral(api_key=self.api_key)

    async def process_pdf(self, file_path: str) -> str:
        """Process PDF using Mistral's document processing capabilities."""
        try:
            print("Processing PDF with Mistral OCR...")
            # Upload the file to Mistral
            with open(file_path, "rb") as file:
                uploaded_file = await self.client.files.upload_async(
                    file={
                        "file_name": os.path.basename(file_path),
                        "content": file,
                    },
                    purpose="ocr"
                )

            # Get signed URL for the uploaded file
            signed_url = await self.client.files.get_signed_url_async(file_id=uploaded_file.id)

            # Process the document using OCR
            ocr_response = await self.client.ocr.process_async(
                model="mistral-ocr-latest",
                document={
                    "type": "document_url",
                    "document_url": signed_url.url,
                }
            )

            # Extract text from OCR response
            ocr_text = ""
            for page in ocr_response.pages:
                if hasattr(page, 'markdown'):
                    ocr_text += page.markdown + "\n\n"
                elif hasattr(page, 'text'):
                    ocr_text += page.text + "\n\n"

            if not ocr_text.strip():
                raise ValueError("No text content could be extracted from OCR response")
            
            print('ocr_text', ocr_text)

            # Extract content using document understanding
            # chat_response = await self.client.chat.complete_async(
            #     model="mistral-large-latest",
            #     messages=[
            #         {
            #             "role": "system",
            #             "content": "You are an expert at understanding and analyzing document content. Please process the following OCR text to extract key information, maintain structure, and improve readability."
            #         },
            #         {
            #             "role": "user",
            #             "content": ocr_text
            #         }
            #     ]
            # )

            # Clean up the uploaded file
            await self.client.files.delete_async(file_id=uploaded_file.id)
            
            print("Mistral OCR processing complete")
            # return chat_response.choices[0].message.content
            return ocr_text

        except Exception as e:
            print(f"Error processing PDF with Mistral: {str(e)}")
            raise

    async def process_text(self, text_content: str) -> str:
        """Process text content with Mistral AI to improve understanding."""
        try:
            print("Processing text content with Mistral...")
            response = await self.client.chat.complete_async(
                model="mistral-large-latest",
                messages=[
                    {"role": "system", "content": "You are an expert at understanding and analyzing text content. Please process the following text to extract key information, maintain structure, and improve clarity."},
                    {"role": "user", "content": text_content}
                ]
            )
            
            print("Mistral text processing complete")
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error in process_text: {str(e)}")
            return text_content  # Return original content if processing fails

    async def process_pdf_content(self, text_content: str) -> str:
        """Process PDF text content with Mistral AI."""
        if not text_content.strip():
            return "No text content could be extracted from the PDF."
        
        return await self.process_text(text_content) 