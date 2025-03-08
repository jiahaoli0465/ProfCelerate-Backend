import os
from mistralai import Mistral

class MistralProcessor:
    def __init__(self):
        """Initialize Mistral client with API key."""
        self.client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))

    async def process_pdf(self, file_path):
        """Process PDF using Mistral's document processing capabilities."""
        try:
            # Upload the file to Mistral
            with open(file_path, "rb") as file:
                uploaded_file = self.client.files.upload(
                    file={
                        "file_name": os.path.basename(file_path),
                        "content": file,
                    },
                    purpose="ocr"
                )

            # Get signed URL for the uploaded file
            signed_url = self.client.files.get_signed_url(file_id=uploaded_file.id)

            # Process the document using OCR
            ocr_response = self.client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "document_url",
                    "document_url": signed_url.url,
                }
            )

            # Extract content using document understanding
            chat_response = self.client.chat.complete(
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
            
            # Clean up the uploaded file
            self.client.files.delete(file_id=uploaded_file.id)
            
            return content

        except Exception as e:
            print(f"Error processing PDF with Mistral: {str(e)}")
            raise

    async def process_text(self, text_content):
        """Process text content with Mistral AI to improve understanding."""
        try:
            chat_response = self.client.chat.complete(
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