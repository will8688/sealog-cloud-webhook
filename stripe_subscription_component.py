"""
Reusable Stripe Subscription Component for Streamlit
====================================================

This component allows users to subscribe to Stripe products by providing price IDs.
It can be used as a standalone component in any Streamlit application.

Usage:
    from stripe_subscription_component import render_subscription_buttons
    
    price_ids = ['price_1234', 'price_5678']
    render_subscription_buttons(
        price_ids=price_ids,
        user_id=st.session_state.get('user_id'),
        stripe_api_key='your_stripe_secret_key',
        success_url='https://yourapp.com/success',
        cancel_url='https://yourapp.com/cancel'
    )
"""

import streamlit as st
import stripe
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class StripeSubscriptionComponent:
    """Reusable Stripe subscription component"""
    
    def __init__(self, stripe_api_key: str, db_manager: Optional[Any] = None):
        """
        Initialize the subscription component
        
        Args:
            stripe_api_key: Your Stripe secret API key
            db_manager: Optional database manager for updating user profiles
        """
        self.stripe_api_key = stripe_api_key
        stripe.api_key = stripe_api_key
        self.db_manager = db_manager
    
    def fetch_price_details(self, price_id: str) -> Optional[Dict]:
        """Fetch details for a specific price"""
        try:
            price = stripe.Price.retrieve(price_id)
            
            # Get product details
            product = None
            if price.product:
                product = stripe.Product.retrieve(price.product)
            
            return {
                'price': price,
                'product': product
            }
        except stripe.error.StripeError as e:
            st.error(f"Error fetching price {price_id}: {str(e)}")
            return None
    
    def render_subscription_button(
        self, 
        price_id: str,
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        success_url: str = None,
        cancel_url: str = None,
        button_text: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Render a subscription button for a specific price
        
        Args:
            price_id: Stripe price ID
            user_email: Optional user's email address
            user_id: Optional user ID for metadata
            customer_id: Optional existing Stripe customer ID
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment is cancelled
            button_text: Optional custom button text
            metadata: Optional additional metadata
        """
        # Fetch price details
        details = self.fetch_price_details(price_id)
        if not details:
            return
        
        price = details['price']
        product = details['product']
        
        # Display product information
        if product:
            st.markdown(f"### {product.name}")
            if product.description:
                st.markdown(product.description)
        
        # Display price information
        if price.unit_amount:
            amount = f"{price.unit_amount / 100:.2f}"
        else:
            amount = "Custom pricing"
        
        if price.recurring:
            interval = price.recurring.interval
            interval_count = price.recurring.interval_count
            
            if interval_count > 1:
                billing_text = f"every {interval_count} {interval}s"
            else:
                billing_text = f"per {interval}"
            
            price_display = f"{amount} {price.currency.upper()} {billing_text}"
            
            if price.recurring.trial_period_days:
                st.markdown(f"**{price_display}**")
                st.markdown(f"*{price.recurring.trial_period_days}-day free trial included*")
            else:
                st.markdown(f"**{price_display}**")
        else:
            st.markdown(f"**{amount} {price.currency.upper()}** (one-time)")
        
        # Create subscription button
        if not button_text:
            button_text = f"Subscribe - {amount} {price.currency.upper()}"
        
        if st.button(button_text, key=f"subscribe_{price_id}_{id(self)}_{datetime.now().timestamp()}", type="primary", use_container_width=True):
            self.create_subscription_session(
                price_id=price_id,
                user_email=user_email,
                user_id=user_id,
                customer_id=customer_id,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata
            )
    
    def create_subscription_session(
        self,
        price_id: str,
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> None:
        """Create a Stripe checkout session for subscription"""
        try:
            # Default URLs if not provided
            if not success_url:
                # Use the base URL from environment or default to localhost
                base_url = os.getenv('BASE_URL')
                success_url = f"{base_url}?subscription_success=true&price_id={price_id}"
            if not cancel_url:
                base_url = os.getenv('BASE_URL')
                cancel_url = f"{base_url}?subscription_cancelled=true"
            
            # Prepare metadata
            session_metadata = {'price_id': price_id}
            if user_id:
                session_metadata['user_id'] = str(user_id)
            if metadata:
                session_metadata.update(metadata)
            
            # Create checkout session
            session_params = {
                'payment_method_types': ['card'],
                'line_items': [{
                    'price': price_id,
                    'quantity': 1,
                }],
                'mode': 'subscription',
                'success_url': success_url,
                'cancel_url': cancel_url,
                'metadata': session_metadata,
                'subscription_data': {
                    'metadata': {
                        'user_id': str(user_id)
                    }
                }
            }
            
            # Use existing customer or email
            if customer_id:
                session_params['customer'] = customer_id
            elif user_email:
                session_params['customer_email'] = user_email
            # If neither customer_id nor email is provided, Stripe will collect email during checkout
            
            checkout_session = stripe.checkout.Session.create(**session_params)
            
            # Redirect to checkout
            st.markdown(f"""
            <meta http-equiv="refresh" content="0; url={checkout_session.url}">
            <script>window.location.href = "{checkout_session.url}";</script>
            """, unsafe_allow_html=True)
            
            st.info("Redirecting to secure checkout...")
            st.stop()
            
        except stripe.error.StripeError as e:
            st.error(f"Stripe error: {str(e)}")
        except Exception as e:
            st.error(f"Error creating checkout session: {str(e)}")
    
    def handle_subscription_callback(self) -> Optional[str]:
        """
        Handle subscription success/cancel callbacks
        
        Returns:
            The price_id if subscription was successful, None otherwise
        """
        if 'subscription_success' in st.query_params:
            price_id = st.query_params.get('price_id')
            
            st.success("🎉 Subscription successful! Your account has been upgraded.")
            st.balloons()
            
            # Clear query parameters
            try:
                del st.query_params['subscription_success']
                if 'price_id' in st.query_params:
                    del st.query_params['price_id']
            except:
                pass
            
            return price_id
            
        elif 'subscription_cancelled' in st.query_params:
            st.warning("Subscription was cancelled. You can try again whenever you're ready.")
            
            # Clear query parameter
            try:
                del st.query_params['subscription_cancelled']
            except:
                pass
            
        return None


def render_subscription_buttons(
    price_ids: List[str],
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    stripe_api_key: Optional[str] = None,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
    db_manager: Optional[Any] = None,
    columns: int = 3
) -> None:
    """
    Render subscription buttons for multiple price IDs
    
    Args:
        price_ids: List of Stripe price IDs to display
        user_id: Optional user ID for tracking
        user_email: Optional user's email (Stripe will collect if not provided)
        stripe_api_key: Stripe API key (uses env var if not provided)
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if payment is cancelled
        db_manager: Optional database manager for updating user profiles
        columns: Number of columns to display prices in
    """
    # Get API key
    if not stripe_api_key:
        stripe_api_key = os.getenv('STRIPE_SECRET_KEY')
    
    if not stripe_api_key:
        st.error("Stripe API key not configured.")
        return
    
    # Get user email from session if not provided
    if not user_email:
        user_email = st.session_state.get('user_email')
    
    # Initialize component
    component = StripeSubscriptionComponent(stripe_api_key, db_manager)
    
    # Handle callbacks first
    price_id = component.handle_subscription_callback()
        
    # Display subscription options
    st.subheader("Choose Your Subscription Plan")
    
    # Create columns
    cols = st.columns(min(columns, len(price_ids)))

    stripe_customer_id = st.session_state.get('stripe_customer_id');

    # Render each price in a column
    for idx, price_id in enumerate(price_ids):
        with cols[idx % len(cols)]:
            component.render_subscription_button(
                price_id=price_id,
                user_email=user_email,
                user_id=user_id,
                customer_id=stripe_customer_id,
                success_url=success_url,
                cancel_url=cancel_url
            )


# Example standalone usage
if __name__ == "__main__":
    st.set_page_config(page_title="Subscription Page", page_icon="💳", layout="wide")
    
    st.title("Premium Subscriptions")
    
    # Example price IDs - replace with your actual price IDs
    example_price_ids = [
        os.getenv('STRIPE_PRICE_ID_BASIC', 'price_basic_example'),
        os.getenv('STRIPE_PRICE_ID_PRO', 'price_pro_example'),
        os.getenv('STRIPE_PRICE_ID_ENTERPRISE', 'price_enterprise_example')
    ]
    
    # Mock user session for example
    if 'user_id' not in st.session_state:
        st.session_state.user_id = 'example_user_123'
        st.session_state.user_email = 'user@example.com'
    
    # Render subscription buttons
    render_subscription_buttons(
        price_ids=example_price_ids,
        user_id=st.session_state.get('user_id'),
        user_email=st.session_state.get('user_email'),
        columns=3
    )