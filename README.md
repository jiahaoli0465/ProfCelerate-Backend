# Flask Backend

This is a Flask-based backend server with basic setup and CORS support.

## Setup

1. Create a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file (optional):

```bash
PORT=5000  # Optional, defaults to 5000 if not set
```

## Running the Server

Start the server by running:

```bash
python app.py
```

The server will start on http://localhost:5000 by default.

## API Endpoints

### Test Endpoint

- URL: `/api/test`
- Method: `GET`
- Response: `{"message": "Flask backend is running successfully!"}`
