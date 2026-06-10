from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from models import RechargeTransaction, RechargeStatus
from models.customer_user import CustomerUser
from models.reward import SpinSource
from core.database import get_db
from core.permissions import get_current_active_user

router = APIRouter()

class RechargeRecordRequest(BaseModel):
    mobile_number: str
    operator: str
    circle: str
    amount: float
    status: RechargeStatus
    provider_reference: Optional[str] = None
    message: Optional[str] = None

class RechargeResponse(BaseModel):
    transaction_id: int
    mobile_number: str
    operator: str
    amount: float
    status: str
    message: Optional[str] = None
    provider_reference: Optional[str] = None

@router.post("/record", response_model=RechargeResponse)
async def record_recharge(
    request: RechargeRecordRequest,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Record a Mobile Recharge handled by the 3rd Party Provider."""
    if not getattr(current_user, 'is_customer', False):
        raise HTTPException(status_code=403, detail="Only customer accounts can record personal recharges")

    if request.amount < 0:
        raise HTTPException(status_code=400, detail="Invalid recharge amount")

    # Determine if this is a bill payment or mobile recharge based on operator name
    bill_operators = {"electricity", "water bill", "dth", "gas", "broadband", "landline",
                      "state_board", "adani", "tata_sky", "dish_tv", "municipal"}
    is_bill = request.operator.lower() in bill_operators
    spin_source = SpinSource.BILL if is_bill else SpinSource.RECHARGE

    transaction = RechargeTransaction(
        customer_id=current_user.id,
        mobile_number=request.mobile_number,
        operator=request.operator,
        circle=request.circle,
        amount=request.amount,
        status=request.status,
        provider_reference_id=request.provider_reference,
        api_response_message=request.message
    )
    db.add(transaction)
    await db.flush()  # get transaction.id before commit

    # Grant spin token if payment is successful
    if request.status == RechargeStatus.SUCCESS:
        from routers.rewards import grant_spin
        await grant_spin(db, customer_id=current_user.id, source=spin_source, source_ref_id=transaction.id)

    await db.commit()
    await db.refresh(transaction)

    return RechargeResponse(
        transaction_id=transaction.id,
        mobile_number=transaction.mobile_number,
        operator=transaction.operator,
        amount=transaction.amount,
        status=transaction.status.value if hasattr(transaction.status, 'value') else transaction.status,
        message=transaction.api_response_message,
        provider_reference=transaction.provider_reference_id
    )

class BBPSWebhookRequest(BaseModel):
    transaction_id: int
    provider_reference: str
    status: str
    amount: Optional[float] = None
    message: Optional[str] = None

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def recharge_webhook(
    hook_data: BBPSWebhookRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Standard Webhook Endpoint for BBPS/Telecom partners.
    The partner's backend will automatically call this URL when the recharge succeeds or fails.
    (In production, ensure you validate their cryptographic signature/HMAC headers.)
    """
    query = select(RechargeTransaction).where(RechargeTransaction.id == hook_data.transaction_id)
    result = await db.execute(query)
    transaction = result.scalars().first()

    if not transaction:
        # Returning 404 tells the provider we didn't find the transaction.
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Update tracking data securely
    if hook_data.provider_reference:
        transaction.provider_reference_id = hook_data.provider_reference
    if hook_data.message:
        transaction.api_response_message = hook_data.message
    
    # Normalize partner status string
    upper_status = hook_data.status.upper()
    if upper_status in ["SUCCESS", "TXN_SUCCESS"]:
        transaction.status = RechargeStatus.SUCCESS
    elif upper_status in ["FAILED", "FAILURE", "TXN_FAILED"]:
        transaction.status = RechargeStatus.FAILED
    
    await db.commit()
    return {"status": "ok", "message": "Webhook received and transaction updated"}

@router.get("/history")
async def get_recharge_history(
    skip: int = 0,
    limit: int = 20,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the user's recharge history"""
    # Safety: Only customers have personal recharge history
    is_customer = getattr(current_user, 'is_customer', False)
    if not is_customer:
        # If an admin hits this, they get an empty list instead of matching against their Admin ID.
        # Alternatively, admins could see all, but they should usually use the admin endpoint.
        # For privacy, return empty list for non-customers on this generic /history endpoint.
        return []

    query = (
        select(RechargeTransaction)
        .where(RechargeTransaction.customer_id == current_user.id)
        .order_by(RechargeTransaction.created_at.desc())
        .offset(skip).limit(limit)
    )
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    return [
        {
            "id": t.id,
            "mobile_number": t.mobile_number,
            "operator": t.operator,
            "amount": t.amount,
            "status": t.status.value if hasattr(t.status, 'value') else t.status,
            "created_at": t.created_at,
            "provider_reference": t.provider_reference_id
        }
        for t in transactions
    ]

@router.get("/mock-provider", response_class=HTMLResponse)
async def mock_provider_checkout(user_id: int, service_type: str = "Recharge"):
    """
    Simulates the Telecom/BBPS Provider's dynamic Web Checkout.
    """
    # Customize labels based on service_type
    id_label = "Mobile Number"
    if service_type == "Electricity":
        id_label = "Consumer ID / CA Number"
    elif service_type == "Water Bill":
        id_label = "Consumer ID"
    elif service_type == "DTH":
        id_label = "Customer ID / VC Number"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Standard BBPS Gateway - {service_type}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, sans-serif; padding: 20px; background: #f0f2f5; color: #333; }}
            .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-width: 400px; margin: 40px auto; }}
            h2 {{ color: #1a1a1a; margin-top: 0; font-size: 20px; }}
            label {{ font-size: 14px; font-weight: 600; color: #666; margin-bottom: 5px; display: block; }}
            input, select {{ width: 100%; padding: 12px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; font-size: 16px; transition: border-color 0.2s; }}
            input:focus {{ outline: none; border-color: #6c5ce7; }}
            button {{ width: 100%; padding: 14px; background: #6c5ce7; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }}
            button:active {{ transform: scale(0.98); }}
            .brand {{ text-align: center; color: #6c5ce7; font-weight: 800; font-size: 24px; margin-bottom: 20px; border-bottom: 2px solid #6c5ce7; display: inline-block; width: 100%; padding-bottom: 10px; }}
            .service-badge {{ background: #eee; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; margin-bottom: 10px; display: inline-block; color: #666; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="brand">Onlineshop Pay</div>
            <div class="service-badge">{service_type.upper()}</div>
            <h2>Standard Bill Payment</h2>
            <form action="/api/v1/recharge/mock-process" method="POST">
                <input type="hidden" name="user_id" value="{user_id}" />
                <input type="hidden" name="operator" value="{service_type}" />
                
                <label>{id_label}</label>
                <input type="text" name="mobile_number" placeholder="Enter {id_label}" required />
                
                <label>Select Bill Provider</label>
                <select name="operator" required>
                    {"<option value='JIO'>Jio</option><option value='AIRTEL'>Airtel</option>" if service_type == 'Recharge' else 
                     "<option value='STATE_BOARD'>State Electricity Board</option><option value='ADANI'>Adani Power</option>" if service_type == 'Electricity' else
                     "<option value='TATA_SKY'>Tata Play</option><option value='DISH_TV'>Dish TV</option>" if service_type == 'DTH' else
                     "<option value='MUNICIPAL'>Municipal Water Board</option>"}
                </select>

                <label>Bill Amount (₹)</label>
                <input type="number" name="amount" placeholder="e.g. 1500" required />
                
                <button type="submit">Process Payment</button>
            </form>
        </div>
    </body>
    </html>
    """

@router.post("/mock-process")
async def mock_provider_process(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Simulates the provider processing the payment and triggering our database natively.
    """
    form_data = await request.form()
    user_id = int(form_data.get("user_id"))
    mobile_number = form_data.get("mobile_number")
    operator = form_data.get("operator")
    amount = float(form_data.get("amount"))
    
    import random
    # Simulate realistic delay
    
    # In a real app, the provider generates a tracking ID before hitting our webhook.
    transaction = RechargeTransaction(
        customer_id=user_id,
        mobile_number=mobile_number,
        operator=operator,
        circle="MUMBAI",  # Mock Circle
        amount=amount,
        status=RechargeStatus.SUCCESS,
        provider_reference_id=f"TXN_{random.randint(100000, 999999)}",
        api_response_message="Recharge Successful via Mock Webview"
    )
    db.add(transaction)
    await db.commit()
    
    # Redirect to success page so the React Native Webview intercepts it
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/v1/recharge/mock-success", status_code=303)

@router.get("/mock-success", response_class=HTMLResponse)
async def mock_provider_success():
    """Dummy success page for the App Webview to intercept."""
    return """
    <html>
        <body style="display:flex; justify-content:center; align-items:center; height:100vh; background:#e8f5e9; font-family:sans-serif;">
            <div style="text-align:center;">
                <h1 style="color:#2e7d32;">Payment Successful!</h1>
                <p>Returning to app...</p>
            </div>
        </body>
    </html>
    """
