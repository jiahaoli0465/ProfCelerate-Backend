# Chinese Learning Platform Backend

A Flask-based backend service for the Chinese learning platform, featuring PDF processing, voice recording analysis, and AI-powered grading using DeepSeek's API.

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- pip (Python package manager)
- Virtual environment (recommended)
- PostgreSQL database
- DeepSeek API key
- Mistral API key (for OCR capabilities)

### Environment Setup

1. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the backend directory:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/dbname
DEEPSEEK_API_KEY=your_deepseek_api_key
MISTRAL_API_KEY=your_mistral_api_key
FLASK_ENV=development
```

### Running the Server

1. Start the development server:

```bash
python app.py
```

The server will start on `http://localhost:5000` by default.

## 📚 API Documentation

### Authentication Endpoints

- `POST /auth/login`: User login
- `POST /auth/register`: User registration
- `POST /auth/logout`: User logout

### Assignment Endpoints

- `GET /assignments`: List all assignments
- `POST /assignments`: Create new assignment
- `GET /assignments/<id>`: Get assignment details
- `PUT /assignments/<id>`: Update assignment
- `DELETE /assignments/<id>`: Delete assignment

### Submission Endpoints

- `POST /submissions`: Submit assignment
- `GET /submissions/<id>`: Get submission details
- `POST /submissions/<id>/grade`: Grade submission

## 🔧 Core Components

### PDF Processing

- Handles PDF file uploads
- Extracts text content
- Supports OCR for image-based PDFs using Mistral

### Voice Recording

- Processes audio file submissions
- Supports common audio formats (MP3, WAV)
- Integrates with speech recognition

### AI Grading System

- Uses DeepSeek API for intelligent grading
- Supports point-based rubrics
- Provides detailed feedback and scoring

## 🧪 Testing

Run the test suite:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=. tests/
```

## 🔍 Code Style

This project follows PEP 8 guidelines. Format your code using:

```bash
black .
flake8 .
```

## 📦 Project Structure

```
backend/
├── app.py              # Main application entry
├── config.py           # Configuration settings
├── requirements.txt    # Dependencies
├── tests/             # Test suite
├── models/            # Database models
├── routes/            # API endpoints
├── services/          # Business logic
│   ├── pdf_service.py
│   ├── voice_service.py
│   └── grading_service.py
└── utils/             # Helper functions
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 🐛 Common Issues

### Database Connection

- Ensure PostgreSQL is running
- Verify database credentials in `.env`
- Check database permissions

### API Keys

- Verify DeepSeek API key is valid
- Ensure Mistral API key has sufficient credits
- Check environment variables are loaded correctly

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.
