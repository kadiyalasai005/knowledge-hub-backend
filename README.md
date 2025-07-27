# Knowledge Hub Backend

A comprehensive document processing and AI-powered chat system built with FastAPI, PostgreSQL, ChromaDB, and Google Cloud services. This backend provides secure document upload, processing, and intelligent chat capabilities using RAG (Retrieval-Augmented Generation).

## 🚀 Features

- **Secure Authentication**: JWT-based authentication with bcrypt password hashing
- **Document Processing**: Upload and process various document formats (PDF, images, etc.)
- **AI-Powered Chat**: Chat with documents using Google's Gemini model
- **Vector Search**: ChromaDB-based semantic search for document retrieval
- **Background Processing**: Celery with Redis for async document processing
- **Cloud Storage**: Google Cloud Storage integration for document storage
- **Document AI**: Google Document AI for intelligent document parsing
- **Multi-User Support**: Isolated document access per user
- **Real-time Status Updates**: SSE (Server-Sent Events) for processing status

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │    │   PostgreSQL    │    │     Redis       │
│   (Port 8000)   │◄──►│   (Port 5432)   │    │   (Port 6379)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   ChromaDB      │    │  Google Cloud   │    │   Celery        │
│  Vector Store   │    │   Storage/AI    │    │   Workers       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🛠️ Tech Stack

- **Backend Framework**: FastAPI 0.115.9
- **Database**: PostgreSQL 15 with SQLAlchemy 2.0
- **Vector Database**: ChromaDB 1.0.7
- **Task Queue**: Celery 5.5.2 with Redis 5.0.7
- **Authentication**: JWT with python-jose
- **Password Hashing**: bcrypt via passlib
- **Document Processing**: Google Document AI, PyMuPDF
- **AI/ML**: Google Vertex AI (Gemini), OpenAI Embeddings
- **Cloud Storage**: Google Cloud Storage
- **Containerization**: Docker & Docker Compose

## 📋 Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Google Cloud Platform account with:
  - Document AI API enabled
  - Vertex AI API enabled
  - Cloud Storage API enabled
  - Service account with appropriate permissions
- OpenAI API key (for embeddings)

## 🔧 Environment Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd knowledge-hub-backend
```

### 2. Create Environment File
Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Then edit the `.env` file with your actual values:

```env
# Database Configuration
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_DB=knowledge_hub_db
POSTGRES_SERVER=db

# Security (CHANGE THESE IN PRODUCTION!)
SECRET_KEY=your_secure_secret_key_here
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Google Cloud Configuration
GCP_PROJECT_ID=your-gcp-project-id
DOCUMENT_AI_PROCESSOR_ID=your-docai-processor-id
DOCUMENT_AI_LOCATION=us
GCS_BUCKET_NAME=your-gcs-bucket-name

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379

# CORS Configuration
BACKEND_CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# Processing Configuration
CHUNK_SIZE_TOKENS=500
CHUNK_OVERLAP_TOKENS=50
TOP_K_RESULTS=3
EMBEDDING_MODEL=text-embedding-004
LLM_MODEL=gemini-1.5-flash
```

### 3. Google Cloud Setup

1. **Create a Service Account**:
   ```bash
   gcloud iam service-accounts create knowledge-hub-sa \
     --display-name="Knowledge Hub Service Account"
   ```

2. **Grant Required Permissions**:
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:knowledge-hub-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/documentai.apiUser"
   
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:knowledge-hub-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:knowledge-hub-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/storage.objectViewer"
   ```

3. **Download Service Account Key**:
   ```bash
   gcloud iam service-accounts keys create ~/.config/gcloud/application_default_credentials.json \
     --iam-account=knowledge-hub-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

4. **Enable Required APIs**:
   ```bash
   gcloud services enable documentai.googleapis.com
   gcloud services enable aiplatform.googleapis.com
   gcloud services enable storage.googleapis.com
   ```

### 4. Create Document AI Processor

```bash
gcloud documentai processors create \
  --location=us \
  --type=document-ocr \
  --display-name="Knowledge Hub OCR Processor"
```

## 🚀 Quick Start

### Using Docker Compose (Recommended)

1. **Start all services**:
   ```bash
   docker-compose up -d
   ```

2. **Run database migrations**:
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

3. **Access the API**:
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/

### Manual Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start PostgreSQL and Redis**:
   ```bash
   docker-compose up -d db redis
   ```

3. **Run migrations**:
   ```bash
   alembic upgrade head
   ```

4. **Start the application**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Start Celery worker** (in separate terminal):
   ```bash
   celery -A tasks.celery_app.celery_app worker --loglevel=info
   ```

## 📚 API Documentation

### Authentication Endpoints

- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/token` - Login and get access token
- `GET /api/v1/auth/users/me` - Get current user details

### Document Endpoints

- `POST /api/v1/documents` - Upload and process document
- `GET /api/v1/documents` - List user's documents
- `GET /api/v1/documents/{doc_id}` - Get document details
- `GET /api/v1/documents/{doc_id}/status` - Get processing status
- `GET /api/v1/documents/{doc_id}/view` - Get document view URL
- `DELETE /api/v1/documents/{doc_id}` - Delete document

### Chat Endpoints

- `POST /api/v1/chat/document/{doc_id}` - Chat with specific document

### Status Updates

- `GET /api/v1/status/stream` - SSE stream for processing updates

## 🔒 Security Features

- **JWT Authentication**: Secure token-based authentication
- **Password Hashing**: bcrypt for secure password storage
- **User Isolation**: Documents are isolated per user
- **Input Validation**: Pydantic schemas for request validation
- **CORS Protection**: Configurable CORS middleware
- **File Type Validation**: Whitelist of allowed file types
- **Secure File Storage**: Google Cloud Storage with signed URLs

## 🛡️ Security Considerations

### Critical Security Requirements

⚠️ **BEFORE DEPLOYING TO PRODUCTION, YOU MUST:**

1. **Change Default Credentials**:
   - Set a strong `SECRET_KEY` in your `.env` file
   - Use strong database passwords
   - Never use default credentials in production

2. **Configure CORS Properly**:
   - Set `BACKEND_CORS_ORIGINS` to your specific frontend domains
   - Never use `*` in production

3. **Secure Database Access**:
   - Database ports are not exposed externally (configured in docker-compose.yml)
   - Use strong database passwords
   - Consider using connection pooling in production

4. **Google Cloud Security**:
   - Use service accounts with minimal required permissions
   - Store credentials securely
   - Enable audit logging for GCP services

5. **Environment Variables**:
   - All sensitive configuration is loaded from environment variables
   - No hardcoded secrets in the codebase
   - Use different credentials for development and production

### Security Best Practices

1. **Authentication & Authorization**:
   - JWT tokens expire after 30 minutes by default
   - User sessions are properly isolated
   - All endpoints require authentication except `/auth/register` and `/auth/token`

2. **File Upload Security**:
   - File type validation prevents malicious uploads
   - Files are stored in isolated user directories
   - Signed URLs expire after 15 minutes

3. **Data Protection**:
   - User data is isolated per user
   - Database uses proper foreign key constraints
   - Vector store data is filtered by user

4. **Network Security**:
   - Database and Redis are not exposed externally
   - Only the API port (8000) is exposed
   - CORS is properly configured

### Security Checklist

- [ ] Set strong `SECRET_KEY` in `.env`
- [ ] Configure `BACKEND_CORS_ORIGINS` for your domains
- [ ] Use strong database passwords
- [ ] Set up Google Cloud service account with minimal permissions
- [ ] Enable HTTPS in production
- [ ] Set up proper logging and monitoring
- [ ] Regular security updates for dependencies
- [ ] Backup strategy for database and files
- [ ] Rate limiting for API endpoints
- [ ] Input sanitization and validation

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key | **Required** |
| `GCP_PROJECT_ID` | Google Cloud Project ID | `None` |
| `OPENAI_API_KEY` | OpenAI API key for embeddings | `None` |
| `DOCUMENT_AI_PROCESSOR_ID` | Document AI processor ID | `None` |
| `GCS_BUCKET_NAME` | Google Cloud Storage bucket | `None` |
| `CHUNK_SIZE_TOKENS` | Document chunk size | `500` |
| `TOP_K_RESULTS` | Number of search results | `3` |

### Database Schema

The application uses two main tables:

- **users**: User authentication and profile data
- **documents**: Document metadata and processing status

## 🐛 Troubleshooting

### Common Issues

1. **Database Connection Error**:
   - Ensure PostgreSQL is running
   - Check database credentials in `.env`

2. **Google Cloud Authentication Error**:
   - Verify service account key is properly mounted
   - Check API permissions are granted

3. **Document Processing Fails**:
   - Verify Document AI processor is created
   - Check file format is supported

4. **Vector Search Issues**:
   - Ensure ChromaDB is accessible
   - Check embedding model configuration

### Logs

View logs for different services:

```bash
# Backend logs
docker-compose logs backend

# Worker logs
docker-compose logs worker

# Database logs
docker-compose logs db
```

## 🧪 Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest
```

### Code Style

```bash
# Install linting tools
pip install black isort flake8

# Format code
black app/
isort app/

# Lint code
flake8 app/
```

## 📦 Deployment

### Production Considerations

1. **Security**:
   - Change default `SECRET_KEY`
   - Use strong passwords
   - Enable HTTPS
   - Configure proper CORS origins

2. **Performance**:
   - Use production-grade PostgreSQL
   - Configure Redis persistence
   - Set up proper monitoring

3. **Scalability**:
   - Use multiple Celery workers
   - Configure load balancing
   - Set up proper backup strategies

### Docker Production Build

```bash
# Build production image
docker build -t knowledge-hub-backend .

# Run with production settings
docker run -p 8000:8000 knowledge-hub-backend
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.


---

**Note**: This is a production-ready backend system. Ensure all security configurations are properly set before deploying to production environments. 