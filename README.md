# Flask Backend

This is a Flask-based backend server with Supabase integration and CORS support.

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

3. Create a `.env` file with your Supabase credentials:

```bash
PORT=5000  # Optional, defaults to 5000 if not set
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
```

To get your Supabase credentials:

1. Go to your Supabase project dashboard
2. Click on the "Settings" icon (gear) in the left sidebar
3. Click on "API" in the settings menu
4. Copy the "Project URL" and "anon/public" key

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

### Data Endpoints

- GET `/api/data`

  - Retrieves all records from the specified table
  - Response: Array of records

- POST `/api/data`
  - Creates a new record
  - Request Body: JSON object with the data to insert
  - Response: Created record
