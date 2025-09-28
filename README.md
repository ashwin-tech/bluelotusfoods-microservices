# Blue Lotus Foods - Microservices

This repository contains the backend microservices for Blue Lotus Foods.

## Services

### bluelotusfoods-api
Main API service handling vendor quotes, products, and business logic.

### bluelotusfoods-email
Email service microservice for sending notifications and quotes.

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL database
- Conda or pip for package management

### Installation

1. Set up Python environment:
```bash
conda create -n bluelotusfoods python=3.11
conda activate bluelotusfoods
```

2. Install dependencies for main API:
```bash
cd bluelotusfoods-api
pip install -r requirements.txt
```

3. Install dependencies for email service:
```bash
cd bluelotusfoods-email
pip install -r requirements.txt
```

### Configuration

Copy and configure environment files:
```bash
# Main API
cp bluelotusfoods-api/.env.example bluelotusfoods-api/.env

# Email Service  
cp bluelotusfoods-email/.env.example bluelotusfoods-email/.env
```

### Running Services

#### Main API Service
```bash
cd bluelotusfoods-api
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
```

#### Email Service
```bash
cd bluelotusfoods-email
uvicorn app.main:app --reload --port 8001 --host 0.0.0.0
```

## API Documentation

- Main API: http://localhost:8000/docs
- Email Service: http://localhost:8001/docs

## Project Structure

```
bluelotusfoods-microservices/
├── bluelotusfoods-api/        # Main API service
│   ├── app/
│   │   ├── api/              # API endpoints
│   │   ├── core/             # Configuration and settings
│   │   ├── db/               # Database models and connection
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic
│   │   └── main.py           # FastAPI application
│   ├── db/migrations/        # Database migrations
│   ├── tests/                # Test files
│   └── requirements.txt      # Python dependencies
├── bluelotusfoods-email/      # Email service
│   ├── app/
│   │   └── main.py           # Email service application
│   └── requirements.txt      # Python dependencies
└── README.md
```

## Technologies Used

- **FastAPI** - Modern Python web framework
- **PostgreSQL** - Primary database
- **Pydantic** - Data validation and settings
- **SQLAlchemy** - Database ORM
- **Uvicorn** - ASGI server

## Environment Variables

### Main API Service
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` - Database configuration
- `CORS_ALLOW_ORIGINS` - CORS allowed origins
- `EMAIL_SERVICE_URL` - Email service endpoint

### Email Service
- Email service specific configuration

## Contributing

1. Create feature branches for new functionality
2. Write tests for new features
3. Update API documentation
4. Submit pull requests for review