# webhook_service.py
# Standalone FastAPI service for handling Stripe webhooks on Railway

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import stripe
import os
import sqlite3
import json
from datetime import datetime

# Initialize FastAPI app
app = FastAPI(title="Sea Log Webhook Service")

# Create subscriptions table on startup
@app.on_event("startup")
async def startup_event():
    create_subscriptions_table()

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
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

def create_subscriptions_table():
    """Create subscriptions table if it doesn't exist"""
    conn, db_type = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        if db_type == 'postgresql':
            query = '''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    stripe_subscription_id VARCHAR(255) NOT NULL,
                    stripe_price_id VARCHAR(255) NOT NULL,
                    status TEXT DEFAULT 'active',
                    stripe_product_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, stripe_subscription_id, stripe_price_id)
                )
            '''
        else:
            # SQLite
            query = '''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    stripe_subscription_id TEXT NOT NULL,
                    stripe_price_id TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    stripe_product_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, stripe_subscription_id, stripe_price_id)
                )
            '''
        
        cursor.execute(query)
        
        # Check if stripe_product_id column exists, if not add it
        if db_type == 'postgresql':
            check_column_query = '''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'subscriptions' AND column_name = 'stripe_product_id'
            '''
            cursor.execute(check_column_query)
            if not cursor.fetchone():
                alter_query = '''
                    ALTER TABLE subscriptions 
                    ADD COLUMN IF NOT EXISTS stripe_product_id VARCHAR(255) NOT NULL DEFAULT ''
                '''
                cursor.execute(alter_query)
                print("Added stripe_product_id column to subscriptions table")
        else:
            # SQLite - check column existence differently
            cursor.execute("PRAGMA table_info(subscriptions)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'stripe_product_id' not in columns:
                alter_query = '''
                    ALTER TABLE subscriptions 
                    ADD COLUMN stripe_product_id TEXT NOT NULL DEFAULT ''
                '''
                cursor.execute(alter_query)
                print("Added stripe_product_id column to subscriptions table")
        
        conn.commit()
        print("Subscriptions table created/updated successfully")
        return True
        
    except Exception as e:
        print(f"Error creating subscriptions table: {e}")
        return False
    finally:
        conn.close()

def update_user_subscription(user_id, stripe_subscription_id):
    """Update user subscription status in database"""
    conn, db_type = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Get the current subscription details from Stripe
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        
        # Get the customer ID from the subscription
        customer_id = subscription.get('customer')

        print(f"Updating subscription for user_id={user_id}, stripe_subscription_id={stripe_subscription_id}, customer_id={customer_id}")
        
        # Update the stripe_customer_id in the users table
        if customer_id:
            update_user_query = "UPDATE users SET stripe_customer_id = %s WHERE id = %s"
            cursor.execute(update_user_query, (customer_id, user_id))
        
        # Delete existing subscriptions for this user
        delete_query = "DELETE FROM subscriptions WHERE user_id = %s"
        cursor.execute(delete_query, (user_id,))
        
        
        # Get all active subscriptions for this customer and insert them
        if customer_id:
            # List all active subscriptions for the customer
            subscriptions = stripe.Subscription.list(
                customer=customer_id,
                status='active',
                limit=100
            )
            
            # Insert each subscription and its price IDs
            for sub in subscriptions.data:
                if sub.get('items'):
                    for item in sub['items']['data']:
                        if item.get('price') and item['price'].get('id'):
                            # Get the product ID from the price
                            product_id = item['price'].get('product', '')
                            
                            insert_query = '''
                                INSERT INTO subscriptions (user_id, stripe_subscription_id, stripe_price_id, stripe_product_id, status)
                                VALUES (%s, %s, %s, %s, 'active')
                                ON CONFLICT (user_id, stripe_subscription_id, stripe_price_id) DO NOTHING
                            '''
                            cursor.execute(insert_query, (user_id, sub['id'], item['price']['id'], product_id))
                           
        
        conn.commit()
        print(f"Updated subscriptions for user {user_id}")
        return True
        
    except Exception as e:
        print(f"Error updating subscription: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

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
        sig_header = request.headers.get('stripe-signature');

        

        print(f"Received webhook sig_header: {sig_header}")

        print(f"Received STRIPE_WEBHOOK_SECRET: {STRIPE_WEBHOOK_SECRET}...")  # Log first 100 bytes for brevity

        print(f"Received payload: {payload[:100]}...")  # Log first 100 bytes for brevity

        print(f"Received STRIPE_SECRET_KEY: {STRIPE_SECRET_KEY}...") 

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
            print(f"Signature verification error: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Handle the event
        print(f"Received webhook event: {event['type']}")
        
        if event['type'] == 'customer.subscription.created':
            # New subscription created
            subscription = event['data']['object']
            user_id = subscription['metadata'].get('user_id')
            if user_id:
                success = update_user_subscription(int(user_id), subscription['id'])
                print(f"Subscription created for user {user_id}: {'success' if success else 'failed'}")
        
        elif event['type'] == 'customer.subscription.updated':
            # Subscription updated (e.g., cancelled)
            subscription = event['data']['object']
            user_id = subscription['metadata'].get('user_id')
            if user_id:
                status = 'cancelled' if subscription['cancel_at_period_end'] else 'active'
                success = update_user_subscription(int(user_id), subscription['id'])
                print(f"Subscription updated for user {user_id}: status={status}, success={success}")
        
        elif event['type'] == 'customer.subscription.deleted':
            # Subscription ended
            subscription = event['data']['object']
            user_id = subscription['metadata'].get('user_id')
            if user_id:
                success = update_user_subscription(int(user_id), subscription['id'])
                print(f"Subscription deleted for user {user_id}: {'success' if success else 'failed'}")
        
        elif event['type'] == 'invoice.payment_succeeded':
            # Payment succeeded
            invoice = event['data']['object']
            print(f"Processing invoice payment succeeded for invoice: {invoice['subscription']}")
            if invoice['subscription']:
                subscription = stripe.Subscription.retrieve(invoice['subscription'])
                user_id = subscription['metadata'].get('user_id')
                if user_id:
                    success = update_user_subscription(int(user_id), subscription['id'])
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
