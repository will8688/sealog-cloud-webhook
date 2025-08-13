# webhook_service.py
# Standalone FastAPI service for handling Stripe webhooks on Railway

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import stripe
import os
import sqlite3
from datetime import datetime

# Initialize FastAPI app
app = FastAPI(title="Sea Log Webhook Service")

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:qZSyDZAgjfOIiDNsVxVlCKfPfnCCkhPU@crossover.proxy.rlwy.net:57261/railway')

# Validate required environment variables
if not stripe.api_key:
    print("ERROR: STRIPE_SECRET_KEY environment variable not set")
    exit(1)

if not STRIPE_WEBHOOK_SECRET:
    print("ERROR: STRIPE_WEBHOOK_SECRET environment variable not set")
    exit(1)

def get_db_connection():
    """Get database connection"""
    try:
        if DATABASE_URL.startswith('postgresql://'):
            # Use PostgreSQL if available on Railway
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(DATABASE_URL)
            return conn, 'postgresql'
        else:
            # Fallback to SQLite
            conn = sqlite3.connect(DATABASE_URL)
            conn.row_factory = sqlite3.Row
            return conn, 'sqlite'
    except Exception as e:
        print(f"Database connection error: {e}")
        return None, None

def execute_query(query, params=None):
    """Execute database query"""
    conn, db_type = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        if db_type == 'postgresql':
            # Convert SQLite-style ? placeholders to PostgreSQL %s
            query = query.replace('?', '%s')
        
        cursor.execute(query, params or [])
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Query execution error: {e}")
        return False
    finally:
        conn.close()

def update_user_subscription(user_id, stripe_subscription_id, status='active'):
    """Update user subscription status in database"""
    try:
        # Get subscription details from Stripe
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        
        current_period_start = datetime.fromtimestamp(subscription.current_period_start)
        current_period_end = datetime.fromtimestamp(subscription.current_period_end)
        
        query = '''
            UPDATE users 
            SET stripe_subscription_id = ?, 
                subscription_status = ?,
                subscription_start = ?,
                subscription_end = ?,
                updated_at = ?
            WHERE id = ?
        '''
        
        params = (
            stripe_subscription_id,
            status,
            current_period_start.isoformat(),
            current_period_end.isoformat(),
            datetime.now().isoformat(),
            user_id
        )
        
        return execute_query(query, params)
        
    except Exception as e:
        print(f"Error updating subscription: {e}")
        return False

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "Webhook service running", "service": "Sea Log Stripe Webhooks"}

@app.post("/webhook/stripe")
async def handle_stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    try:
        # Get the raw body and signature header
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')

        print(f"Received webhook sig_header: {sig_header}")
        
        if not sig_header:
            raise HTTPException(status_code=400, detail="Missing signature header")
        
        # Verify the webhook signature
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Handle the event
        print(f"Received webhook event: {event['type']}")
        
        if event['type'] == 'customer.subscription.created':
            # New subscription created
            subscription = event['data']['object']
            user_id = subscription['metadata'].get('user_id')
            if user_id:
                success = update_user_subscription(int(user_id), subscription['id'], 'active')
                print(f"Subscription created for user {user_id}: {'success' if success else 'failed'}")
        
        elif event['type'] == 'customer.subscription.updated':
            # Subscription updated (e.g., cancelled)
            subscription = event['data']['object']
            user_id = subscription['metadata'].get('user_id')
            if user_id:
                status = 'cancelled' if subscription['cancel_at_period_end'] else 'active'
                success = update_user_subscription(int(user_id), subscription['id'], status)
                print(f"Subscription updated for user {user_id}: status={status}, success={success}")
        
        elif event['type'] == 'customer.subscription.deleted':
            # Subscription ended
            subscription = event['data']['object']
            user_id = subscription['metadata'].get('user_id')
            if user_id:
                success = update_user_subscription(int(user_id), subscription['id'], 'cancelled')
                print(f"Subscription deleted for user {user_id}: {'success' if success else 'failed'}")
        
        elif event['type'] == 'invoice.payment_succeeded':
            # Payment succeeded
            invoice = event['data']['object']
            if invoice['subscription']:
                subscription = stripe.Subscription.retrieve(invoice['subscription'])
                user_id = subscription['metadata'].get('user_id')
                if user_id:
                    success = update_user_subscription(int(user_id), subscription['id'], 'active')
                    print(f"Payment succeeded for user {user_id}: {'success' if success else 'failed'}")
        
        elif event['type'] == 'invoice.payment_failed':
            # Payment failed
            invoice = event['data']['object']
            if invoice['subscription']:
                subscription = stripe.Subscription.retrieve(invoice['subscription'])
                user_id = subscription['metadata'].get('user_id')
                if user_id:
                    query = "UPDATE users SET subscription_status = ? WHERE id = ?"
                    success = execute_query(query, ('payment_failed', int(user_id)))
                    print(f"Payment failed for user {user_id}: {'updated' if success else 'failed to update'}")
        
        return JSONResponse(content={"status": "success"})
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check for Railway deployment"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
