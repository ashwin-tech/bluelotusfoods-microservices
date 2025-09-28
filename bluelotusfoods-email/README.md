# Blue Lotus Foods Email Service

A microservice for handling automated email notifications with PDF attachments.

## Features

- Send vendor quote confirmations with PDF attachments
- Template-based email composition
- PDF generation from quote data
- Configurable SMTP settings
- Structured logging
- Environment-based configuration

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables (copy `.env.example` to `.env`)

3. Run the service:
```bash
uvicorn app.main:app --reload --port 8001
```

## API Endpoints

- `POST /email/vendor-quote` - Send vendor quote email with PDF
- `GET /health` - Health check endpoint

## Environment Variables

- `SMTP_SERVER` - SMTP server address
- `SMTP_PORT` - SMTP server port
- `SMTP_USERNAME` - SMTP username
- `SMTP_PASSWORD` - SMTP password
- `SMTP_USE_TLS` - Enable TLS (true/false)
- `FROM_EMAIL` - Sender email address
- `FROM_NAME` - Sender name