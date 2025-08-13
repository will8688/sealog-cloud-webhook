# Railway Webhook Service Deployment Guide

## Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **Railway CLI** (optional but recommended): 
   ```bash
   npm install -g @railway/cli
   railway login
   ```

## Deployment Steps

### Method 1: Railway Dashboard (Recommended)

1. **Create New Project**:
   - Go to Railway Dashboard
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Connect your SeaLog-Cloud-Production repository

2. **Configure Service**:
   - Railway will detect your app automatically
   - For webhook service, you may need to create a separate service
   - Click "New Service" → "GitHub Repo" → Select your repo
   - Set the **Root Directory** to `webhook`

3. **Set Environment Variables**:
   Go to your service → Variables tab and add:
   ```
   STRIPE_SECRET_KEY=sk_live_your_actual_stripe_secret_key
   STRIPE_WEBHOOK_SECRET=whsec_your_actual_webhook_secret
   DATABASE_URL=postgresql://your_database_connection_string
   PORT=8000
   ```

4. **Deploy**:
   - Railway will automatically build and deploy
   - Your webhook will be available at: `https://your-service-name.railway.app`

### Method 2: Railway CLI

1. **Initialize Railway Project**:
   ```bash
   cd webhook
   railway login
   railway init
   ```

2. **Set Environment Variables**:
   ```bash
   railway variables set STRIPE_SECRET_KEY=sk_live_your_key
   railway variables set STRIPE_WEBHOOK_SECRET=whsec_your_secret
   railway variables set DATABASE_URL=postgresql://your_db_url
   ```

3. **Deploy**:
   ```bash
   railway up
   ```

## Environment Variables Required

| Variable | Description | Example |
|----------|-------------|---------|
| `STRIPE_SECRET_KEY` | Your Stripe secret key | `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Webhook endpoint secret | `whsec_...` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:port/db` |
| `PORT` | Port (Railway sets automatically) | `8000` |

## Stripe Webhook Configuration

1. **Go to Stripe Dashboard**:
   - Navigate to Developers → Webhooks
   - Click "Add endpoint"

2. **Configure Endpoint**:
   - **URL**: `https://your-webhook-service.railway.app/webhook/stripe`
   - **Events to send**:
     - `customer.subscription.created`
     - `customer.subscription.updated` 
     - `customer.subscription.deleted`
     - `invoice.payment_succeeded`
     - `invoice.payment_failed`

3. **Get Webhook Secret**:
   - After creating, click on the webhook
   - Copy the "Signing secret" (starts with `whsec_`)
   - Set this as `STRIPE_WEBHOOK_SECRET` in Railway

## Health Check Endpoints

- **Basic Status**: `GET /`
- **Health Check**: `GET /health`
- **Webhook Endpoint**: `POST /webhook/stripe`

## Testing the Webhook

1. **Check if service is running**:
   ```bash
   curl https://your-webhook-service.railway.app/health
   ```
   
2. **Test with Stripe CLI** (optional):
   ```bash
   stripe listen --forward-to https://your-webhook-service.railway.app/webhook/stripe
   ```

## Troubleshooting

### Common Issues:

1. **Build Fails**:
   - Check that `requirements.txt` includes all dependencies
   - Ensure Python version compatibility

2. **Environment Variables Not Set**:
   - Verify all required variables are set in Railway dashboard
   - Check variable names match exactly

3. **Database Connection Issues**:
   - Ensure `DATABASE_URL` is correctly formatted
   - Check database is accessible from Railway

4. **Webhook Not Receiving Events**:
   - Verify webhook URL in Stripe dashboard
   - Check webhook secret matches
   - Review Railway logs for errors

### Viewing Logs:
```bash
railway logs
```
Or view in Railway Dashboard → Service → Logs

## Separate Services Strategy

For better architecture, consider running:

1. **Main App Service**: Streamlit application
   - Root directory: `/` (main project)
   - Start command: `streamlit run main.py --server.port=$PORT --server.address=0.0.0.0`

2. **Webhook Service**: FastAPI webhook handler  
   - Root directory: `/webhook`
   - Start command: `python webhook_service.py`

This allows independent scaling and deployment of each service.

## Security Notes

- Never commit real API keys to version control
- Use Railway's environment variables for sensitive data
- Regularly rotate webhook secrets and API keys
- Monitor webhook endpoint logs for suspicious activity

## Cost Optimization

- Railway offers a free tier suitable for testing
- Production usage may require paid plans
- Consider using Railway's database service for better integration