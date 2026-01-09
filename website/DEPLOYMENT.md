# Deployment Guide for AWS

This guide walks you through deploying the personal website to AWS.

## Option 1: Full-Stack Deployment (EC2/Elastic Beanstalk)

### Prerequisites
- AWS Account
- Domain name (masonlancellotti.com) configured
- AWS CLI installed

### Steps

#### 1. Backend Setup (Flask API)

1. **Create Elastic Beanstalk Application** (or use EC2):
   ```bash
   # Install EB CLI
   pip install awsebcli
   
   # Initialize EB in backend directory
   cd backend
   eb init -p python-3.11 flask-api --region us-east-1
   eb create flask-api-env
   ```

2. **Configure environment variables** (if needed):
   - Set PORT in Elastic Beanstalk configuration
   - Update TRADING_BOT_PATH if deploying backend separately

3. **Deploy backend**:
   ```bash
   eb deploy
   ```

#### 2. Frontend Setup (React + S3 + CloudFront)

1. **Build React app**:
   ```bash
   cd frontend
   npm install
   npm run build
   ```

2. **Create S3 bucket**:
   ```bash
   aws s3 mb s3://masonlancellotti-website
   ```

3. **Upload built files**:
   ```bash
   aws s3 sync dist/ s3://masonlancellotti-website --delete
   ```

4. **Enable static website hosting**:
   ```bash
   aws s3 website s3://masonlancellotti-website --index-document index.html
   ```

5. **Create CloudFront distribution**:
   - Go to CloudFront console
   - Create distribution
   - Origin: S3 bucket (masonlancellotti-website)
   - Default root object: index.html
   - Error pages: 404 -> /index.html (for React Router)

6. **Update API URL** in frontend:
   - Update `VITE_API_URL` in `.env.production` to point to your backend API
   - Or set it during build: `VITE_API_URL=https://api.masonlancellotti.com npm run build`

#### 3. Domain Configuration

1. **Route 53 Setup**:
   - Create hosted zone for masonlancellotti.com
   - Add A record pointing to CloudFront distribution
   - Add CNAME for www.masonlancellotti.com

2. **SSL Certificate**:
   - Request certificate in AWS Certificate Manager
   - Validate domain ownership
   - Attach to CloudFront distribution

3. **Update DNS**:
   - Point domain nameservers to Route 53

## Option 2: Simple S3 + CloudFront (Static Only)

If you want to serve the backend separately or use a different service:

1. Build frontend with production API URL
2. Upload to S3
3. Configure CloudFront
4. Point domain to CloudFront

## Environment Variables

### Frontend (.env.production)
```
VITE_API_URL=https://your-api-domain.com/api
```

### Backend
```
PORT=5000
FLASK_ENV=production
```

## Testing Locally

1. **Start backend**:
   ```bash
   cd backend
   pip install -r requirements.txt
   python app.py
   ```

2. **Start frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. Visit `http://localhost:3000`

## Troubleshooting

- **CORS errors**: Ensure flask-cors is installed and CORS(app) is in app.py
- **API not found**: Check VITE_API_URL matches your backend URL
- **Trade data not loading**: Verify TRADING_BOT_PATH in app.py points to correct directory
- **404 on refresh**: Configure CloudFront error pages to return index.html for 404s

