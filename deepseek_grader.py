from openai import OpenAI
import os
import json
from typing import Dict, Any
from dotenv import load_dotenv

class DeepSeekGrader:
    def __init__(self):
        """Initialize the DeepSeek grader with API credentials."""
        load_dotenv()
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        if not self.api_key:
            raise ValueError("Missing DEEPSEEK_API_KEY environment variable")
            
        print(f"Initializing DeepSeek client with API key starting with: {self.api_key[:4]}...")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
    
    async def grade_submission(self, content: str, grading_criteria: str, total_points_available: float) -> Dict[str, Any]:
        """Grade content using DeepSeek's API."""
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": """You are an expert grader. When grading submissions, first analyze the content and criteria carefully, then provide your response in two sections:

<reasoning>
1. Break down each aspect/question from the grading criteria
2. Evaluate how well the submission meets each criterion
3. Justify point allocations based on the defined rubric
4. Consider partial credit where appropriate
</reasoning>

<response>
{
    "results": [
        {
            "question": "Question/Aspect being graded [point value]",
            "mistakes": ["List of specific mistakes or areas for improvement"],
            "score": number (based on rubric point allocation),
            "feedback": "Detailed, constructive feedback explaining point allocation"
        }
    ],
    "totalScore": number (sum of all scores),
    "overallFeedback": "Comprehensive overall feedback with suggestions for improvement"
}
</response>

Your JSON response must be within the <response> tags and follow the exact format shown above.
Be thorough in your grading and provide specific, actionable feedback for each aspect."""},
                    {"role": "user", "content": f"""Please grade this submission according to the following rubric:

Grading Criteria:
{grading_criteria}

Total Points Available: {total_points_available}

Submission Content:
{content}

Remember to:
1. Grade each aspect according to its defined point values
2. Provide specific feedback for point deductions
3. Consider partial credit based on the rubric
4. Ensure total score doesn't exceed {total_points_available} points"""}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            return self._parse_grading_response(response.choices[0].message.content, total_points_available)
        except Exception as e:
            print(f"Error grading with DeepSeek: {str(e)}")
            return self._create_error_response(str(e))
    
    def _parse_grading_response(self, response_content: str, total_points_available: float) -> Dict[str, Any]:
        """Parse and validate the grading response."""
        try:
            # Try to extract JSON from <response> tags
            start_tag = "<response>"
            end_tag = "</response>"
            start_idx = response_content.find(start_tag)
            end_idx = response_content.find(end_tag)
            
            if start_idx >= 0 and end_idx > start_idx:
                # Extract and parse JSON content
                json_str = response_content[start_idx + len(start_tag):end_idx].strip()
                result = json.loads(json_str)
            else:
                # Fallback to looking for JSON structure if tags aren't found
                start_idx = response_content.find('{')
                end_idx = response_content.rfind('}') + 1
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = response_content[start_idx:end_idx]
                    result = json.loads(json_str)
                else:
                    raise ValueError("No JSON structure found in response")
        except json.JSONDecodeError as json_error:
            print(f"JSON parsing error: {str(json_error)}")
            print(f"Response content: {response_content}")
            return self._create_fallback_response(response_content, total_points_available)
        
        return self._validate_result(result)
    
    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and ensure the grading result has the expected structure."""
        return {
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
    
    def _create_fallback_response(self, response_content: str, total_points_available: float) -> Dict[str, Any]:
        """Create a fallback response when JSON parsing fails."""
        return {
            "results": [
                {
                    "question": "Submission evaluation",
                    "mistakes": ["Could not parse grading response"],
                    "score": total_points_available * 0.5,  # Give 50% as a fallback
                    "feedback": response_content
                }
            ],
            "totalScore": total_points_available * 0.5,
            "overallFeedback": response_content
        }
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create an error response when grading fails."""
        return {
            "results": [
                {
                    "question": "Error in grading",
                    "mistakes": ["Could not process submission"],
                    "score": 0,
                    "feedback": f"Error during grading: {error_message}"
                }
            ],
            "totalScore": 0,
            "overallFeedback": f"An error occurred during grading: {error_message}"
        } 