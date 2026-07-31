# Ecom Backend API

## Project Structure
```
Ecom_Backend_API/
├── main.py                    # FastAPI entry point
├── .env                       # Environment config
├── core/                      # Config, security, DB, permissions
├── models/                    # SQLAlchemy models (25+ tables)
├── schemas/                   # Pydantic request/response schemas
├── routers/                   # API route handlers (32 files)
├── services/                  # Business logic services
├── auction/                   # Customer auction module
├── b2b_auction/               # B2B auction module
└── migrations/                # SQL migrations
```

## Tech Stack
- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL (`onlineshopappdb`)
- **Auth**: JWT (HS256) + Argon2 password hashing
- **ORM**: SQLAlchemy (async)
- **Customer Auth**: OTP-based (no password)
- **Staff Auth**: Email/Phone + Password

---

## All User Roles (38 roles)

### System-Level
| Role | Description |
|------|-------------|
| `SUPER_ADMIN` | Full system access |
| `ADMIN` | General admin |
| `ADMIN_USER` | Limited admin |

### Dealer (Seller) Roles
| Role | Description |
|------|-------------|
| `DEALER` | Primary dealer/owner |
| `DEALER_MANAGER` | Operations manager |
| `DEALER_INVENTORY` | Inventory management |
| `DEALER_ORDERS` | Order processing |
| `DEALER_FINANCE` | Financial management |

### Delivery / Hub Roles
| Role | Description |
|------|-------------|
| `DELIVERY_PARTNER` | Delivery partner |
| `HUB` | Hub staff |
| `HUB_MANAGER` | Hub manager |
| `HUB_STAFF` | Hub staff |
| `HUB_DISPATCHER` | Hub dispatcher |
| `HUB_RETURNS` | Hub returns |

### Logistics Roles
| Role | Description |
|------|-------------|
| `RIDER` | Delivery rider |
| `LOGISTICS_ADMIN` | Logistics admin |
| `LOGISTICS_MANAGER` | Logistics manager |

### Showroom Roles
| Role | Description |
|------|-------------|
| `SHOWROOM_MANAGER` | Showroom manager |
| `SHOWROOM_STAFF` | Showroom staff |

### Partner Helpdesk Roles
| Role | Description |
|------|-------------|
| `PARTNER_HELPDESK_OPERATOR` | Helpdesk operator |
| `PARTNER_HELPDESK_SUPERVISOR` | Helpdesk supervisor |
| `PARTNER_HELPDESK_MANAGER` | Helpdesk manager |
| `PARTNER_BACKOFFICE` | Backoffice expert |
| `PARTNER_LOGISTICS_SPECIALIST` | Logistics specialist |
| `PARTNER_FINANCE_SPECIALIST` | Finance specialist |
| `PARTNER_CATALOG_MANAGER` | Catalog manager |
| `PARTNER_TECH_SUPPORT` | Tech support |
| `PARTNER_SUPPORT_MANAGER` | Support manager |

### Customer
| Role | Description |
|------|-------------|
| `CUSTOMER` | End customer/buyer |

---

## Database Users (All Logins)

### Admins & Super Admin
| ID | Email | Name | Role | Phone |
|----|-------|------|------|-------|
| 9 | `superadmin@myntra.com` | Super Admin | SUPER_ADMIN | 9999900000 |
| 3 | `admin@myntra.com` | Admin User | ADMIN | 9876543212 |
| 5 | `admin@example.com` | Admin User | ADMIN | 9876544222 |

### Dealers
| ID | Email | Name | Role | Business | Approved |
|----|-------|------|------|----------|----------|
| 10 | `dealer@myntra.com` | Demo Dealer | DEALER | Demo Electronics Store | ✅ |
| 1 | `dealer_1@test.com` | Test Dealer | DEALER | (no profile) | ✅ |
| 38 | `manitrick@gmail.com` | MAARAN | DEALER | CST Dealer | ✅ |

### Riders
| ID | Email | Name | Role | Phone | Active |
|----|-------|------|------|-------|--------|
| 34 | `rider3@example.com` | Rider 3 | RIDER | 9876543211 | ✅ |
| 36 | `raj@rider.com` | Raj log | RIDER | 9876543216 | ✅ |
| 16 | `vijay@rider.com` | Vijay | RIDER | 9876543210 | ✅ |
| 13 | `rider@myntra.com` | Demo Rider | DELIVERY_PARTNER | 9999900004 | ❌ |
| 32 | `rider1@example.com` | Rider 1 | RIDER | - | ❌ |
| 33 | `rider2@example.com` | Rider 2 | RIDER | - | ❌ |

### Hub Staff
| ID | Email | Name | Role | Dealer | Hub ID |
|----|-------|------|------|--------|--------|
| 15 | `hub@hub.com` | Hub | HUB_MANAGER | Demo Electronics | 3 |
| 19 | `showroom@showroom.com` | Chennai ShowRoom | HUB_MANAGER | Demo Electronics | 5 |
| 22 | `showroom@showroom..com` | show room 1 | SHOWROOM_MANAGER | Demo Electronics | 5 |
| 48 | `hubstaff@hub.com` | Hub staff | HUB_STAFF | Demo Electronics | 3 |
| 107 | `mainhub@hub.com` | Main hub | HUB_STAFF | Demo Electronics | 16 |

### Logistics
| ID | Email | Name | Role | Partner ID |
|----|-------|------|------|------------|
| 35 | `logistics@example.com` | Logistics Admin | LOGISTICS_ADMIN | 1 |
| 37 | `staff@logistics.com` | Staff log | LOGISTICS_MANAGER | 1 |

### Partner Helpdesk (myntra.com domain)
| ID | Email | Name | Role |
|----|-------|------|------|
| 93 | `operator1@myntra.com` | Helpdesk Operator 1 | PARTNER_HELPDESK_OPERATOR |
| 94 | `operator2@myntra.com` | Helpdesk Operator 2 | PARTNER_HELPDESK_OPERATOR |
| 95 | `operator3@myntra.com` | Helpdesk Operator 3 | PARTNER_HELPDESK_OPERATOR |
| 96 | `operator4@myntra.com` | Helpdesk Operator 4 | PARTNER_HELPDESK_OPERATOR |
| 97 | `operator5@myntra.com` | Helpdesk Operator 1 | PARTNER_HELPDESK_OPERATOR |
| 98 | `operator@myntra.com` | Helpdesk Operator 1 | PARTNER_HELPDESK_OPERATOR |
| 99 | `supervisor@myntra.com` | Helpdesk Supervisor 1 | PARTNER_HELPDESK_SUPERVISOR |
| 100 | `manager@myntra.com` | Helpdesk Manager 1 | PARTNER_HELPDESK_MANAGER |
| 101 | `backoffice@myntra.com` | Backoffice Expert 1 | PARTNER_BACKOFFICE |
| 102 | `logistics@myntra.com` | Logistics Specialist 1 | PARTNER_LOGISTICS_SPECIALIST |
| 103 | `finance@myntra.com` | Finance Specialist 1 | PARTNER_FINANCE_SPECIALIST |
| 104 | `catalog@myntra.com` | Catalog Manager 1 | PARTNER_CATALOG_MANAGER |
| 105 | `tech@myntra.com` | Tech Support 1 | PARTNER_TECH_SUPPORT |
| 106 | `support_manager@myntra.com` | Support Manager 1 | PARTNER_SUPPORT_MANAGER |

### Partner Helpdesk (helpdesk.com domain)
| ID | Email | Name | Role |
|----|-------|------|------|
| 79-88 | `agent1` thru `agent10@helpdesk.com` | Helpdesk Agent 1-10 | partner_helpdesk_operator |

### Customers (separate `customer_users` table - OTP login)
| ID | Phone | Name |
|----|-------|------|
| 9 | 9876543211 | Mani |
| 8 | 9876543210 | Test Customer 3 |
| 12 | 9845689256 | hemanth |
| 13 | 7200041005 | Priya |
| 14 | 8095215111 | hemanth1 |
| 15 | 9845244499 | hemanth2 |
| 16 | 9876543212 | Maran |
| 10 | 1234567617 | Test Customer |
| 47 | 1234567813 | Test Customer |

---

## Authentication Workflows

### 1. Customer Login (OTP-based)
```
LoginScreen -> Customer tab
  Enter 10-digit mobile
  POST /api/v1/auth/customer/login-request  -> OTP via SMS
  Enter 6-digit OTP
  POST /api/v1/auth/customer/login-verify   -> JWT returned
  Navigate to UserTabNavigator (Home)
```

### 2. Customer Registration (OTP-based)
```
RegisterScreen
  Step 1: Name + Mobile + (optional referral code)
  Step 2: POST /auth/customer/register-request -> OTP
  Step 3: POST /auth/customer/register-verify  -> creates account, returns JWT
  Auto-login -> Home
```

### 3. Staff Login (Email + Password)
```
[Role]LoginScreen (Admin/Dealer/Rider/Hub/Showroom/Logistics)
  Enter email + password
  POST /api/v1/auth/login
  Server validates role matches expected portal
  JWT returned with role + user data
  Navigate to respective Dashboard
```

**OTP codes for testing**: `123456` or `654321` (bypass SMS)

### 4. Dealer Registration
```
DealerSignupScreen
  Step 1: Business Name, GST, PAN, Address
  Step 2: Owner Name, Phone, Email, Password
  POST /auth/send-otp -> verify email
  POST /auth/verify-otp
  POST /auth/dealer-register
    -> User created (is_active=False)
    -> Dealer created (is_approved=False, access_status='pending')
    -> Default DeliveryHub auto-created
  Navigate to DealerLogin
```

### 5. Forgot/Change Password
```
DealerLoginScreen -> "Forgot/Change Password"
  POST /auth/send-otp -> OTP to email
  VerifyDealerOTPScreen -> POST /auth/verify-otp
  SetDealerPasswordScreen -> POST /auth/set-dealer-password
```

### 6. Account Reactivation
```
Post-login error "account_deactivated"
  ReactivateAccountScreen
  POST /auth/reactivate-request -> OTP
  POST /auth/verify-reactivation
```

---

## Complete End-to-End Product Workflow (Dealer → Customer → Return)

This section covers the full journey: how a dealer adds a product, how it gets approved and reaches customers, how a customer buys it, how GST is calculated at every step, and what happens if they cancel, return, or exchange it.

### Tax System Overview (Relevant Throughout)

Before the workflow, understand the tax models:

```
TaxCategory (tax slab e.g., "GST 18%")
  ├── cgst_rate: 9.0   (Central GST)
  ├── sgst_rate: 9.0   (State GST)
  ├── igst_rate: 18.0  (Integrated GST - inter-state)

TaxRule (maps slab to products)
  ├── category_id -> applies to all products in a category
  ├── product_id  -> applies to a specific product (overrides category)
  ├── priority    -> higher wins if multiple match
  └── tax_category_id -> FK to TaxCategory

TaxLedger (audit trail - one per order item)
  ├── taxable_amount, cgst_amount, sgst_amount, igst_amount
  ├── total_tax, hsn_code
```

**Tax rate lookup priority**:
1. Product-specific rule (if `product.tax_rule_id` is set)
2. Category-level rule (matched to `product.category_id`)
3. Parent category rule (walked up recursively)
4. Default: 0%

**Intra vs Inter state**:
- Same state → CGST + SGST (split equally)
- Different state → IGST (full rate)

**Price is inclusive** of tax. Example at 18% GST:
- Customer pays ₹1180 → taxable_amount = ₹1000, tax = ₹180

---

### PHASE 1: DEALER ONBOARDING (Pre-requisite)

```
1. DEALER REGISTRATION (Frontend: DealerSignupScreen)
   Step 1: Enter Business Name, GST Number, PAN, Address
   Step 2: Enter Owner Name, Phone, Email, Password
   POST /auth/send-otp -> OTP sent to email for verification
   POST /auth/verify-otp -> Email verified
   POST /auth/dealer-register
     Backend creates:
       a) User record (role=DEALER, is_active=False)
       b) Dealer record (is_approved=False, access_status='pending')
       c) Default DeliveryHub auto-created
   -> Navigate to DealerLoginScreen

2. ADMIN REVIEWS DEALER (Frontend: AdminDealerApprovals)
   GET /api/v1/admin/pending-approvals -> Lists all pending dealers
   Admin reviews documents: GST cert, PAN, address proof, etc.

3. ADMIN APPROVES DEALER
   PUT /api/v1/admin/dealers/{id}/approve
     Backend does:
       a) Dealer.is_approved = TRUE
       b) Dealer.access_status = 'active'
       c) Dealer.profile_status = 'completed'
       d) Auto-creates DeliveryHub if missing
       e) Sends email notification: "Your dealer account is approved"
   -> Dealer can now login and access full dashboard

   OR ADMIN REJECTS
   PUT /api/v1/admin/dealers/{id}/reject
     -> Dealer.access_status = 'reject'
     -> reject_reason recorded with timestamp
     -> Email sent with rejection reason
```

---

### PHASE 2: PRODUCT CREATION (Dealer adds a product — Tax setup begins here)

```
1. DEALER LOGS IN (Frontend: DealerLoginScreen)
   POST /api/v1/auth/login -> JWT returned with role='dealer', dealer_id
   -> Navigates to DealerDashboard

2. DEALER NAVIGATES TO "ADD NEW PRODUCT"
   Frontend: DealerSidebar -> PRODUCT MANAGEMENT -> Add New Product

3. DEALER FILLS PRODUCT FORM
   Fields:
     - Product Name
     - Description
     - Category (e.g., Electronics > Mobile Phones)
     - Subcategory (optional)
     - Brand
     - MRP (Maximum Retail Price)
     - Selling Price
     - Dealer Price (their cost)
     - SKU (Stock Keeping Unit) - optional
     - Stock Quantity
     - Images (upload multiple)
     - Attributes (dynamic based on category, e.g., Color, Size, RAM, Storage)
       - Mandatory attributes are validated on frontend & backend
     - Variants (optional): Create child products with different attribute combos
       e.g., iPhone 14 - 128GB Black, iPhone 14 - 256GB Blue
     - Return Policy settings:
       - is_returnable (boolean)
       - return_window_days (default 7)
       - is_exchangeable (boolean)
     - Estimated Delivery Days
     - HSN Code (Harmonized System Nomenclature for tax classification)
     - Tax Rule ID (optional — overrides category-level tax for this product)
     - Referral Commission Rate (override)

4. DEALER SUBMITS PRODUCT
   POST /api/v1/products
     Backend does:

     a) VALIDATE CATEGORY EXISTS
        Check category_id is valid in DB

     b) FETCH MANDATORY ATTRIBUTES
        Uses recursive CTE to walk up category hierarchy
        (parent categories -> grandparent -> etc.)
        Also fetches spec group attributes
        Checks all mandatory attributes are provided

     c) AUTO-ASSIGN DEALER
        If current_user.role == DEALER:
          Find Dealer by user_id
          Check dealer.is_active == True (else reject)
          Set db_product.dealer_id = dealer.id
        If current_user.role == ADMIN/SUPER_ADMIN:
          Use provided dealer_id or default to 1

     d) CREATE PRODUCT RECORD
        INSERT INTO products (name, description, price, stock, 
          is_approved=FALSE, dealer_id, category_id, 
          hsn_code=product.hsn_code,       # <-- TAX: HSN code stored
          tax_rule_id=product.tax_rule_id,  # <-- TAX: Optional override
          ...)
        Default state: is_approved = FALSE

     e) CREATE VARIANTS (if provided)
        For each variant:
          - Merge parent attributes + variant attributes
          - Calculate price (dealer_price + price_adjustment)
          - Create child Product with parent_product_id = parent.id
          - Variants inherit: hsn_code, tax_rule_id from parent
          - Variants share same: category, brand, dealer, is_approved

     f) COMMIT TO DATABASE
        Product saved with is_approved = FALSE
        TAX: HSN code set. Tax rule reference stored (or null = use category default).

   Response: Product object with all details
   -> Frontend shows success message
   -> Product appears in dealer's "All Products" list (with "Pending Approval" badge)

5. DEALER CAN EDIT/DELETE PRODUCT (while pending)
   PUT /api/v1/products/{id} -> Update fields, replace variants
   DELETE /api/v1/products/{id} -> Soft delete if has orders, else hard delete
```

---

### PHASE 3: ADMIN PRODUCT APPROVAL

```
1. ADMIN LOGS IN (Frontend: AdminLoginScreen)
   POST /api/v1/auth/login -> JWT returned
   Navigate to AdminDashboard

2. ADMIN REVIEWS PENDING PRODUCTS
   GET /api/v1/admin/pending-approvals -> Shows pending dealers + products
   OR
   GET /api/v1/admin/products?is_approved=false -> All unapproved products
     Shows: name, images, price, dealer name, category, created date, HSN code

3. ADMIN CLICKS ON A PRODUCT TO REVIEW
   Frontend: Product detail view with:
     - All product images
     - Pricing (MRP vs Selling)
     - Category & attributes
     - Stock level
     - Variants (if any)
     - Dealer info
     - HSN Code (tax classification — admin can verify it's correct)
     - Tax Rule (if a product-specific override was set)

   Note: Admin can also configure tax at the CATEGORY level separately:
     POST /api/v1/admin/tax-categories  -> Create tax slab (e.g., GST 18%)
     POST /api/v1/admin/tax-rules       -> Map category to tax slab
     These are done outside the product approval flow, but they determine
     what tax rate applies when this product is sold.

4A. ADMIN APPROVES PRODUCT
    PUT /api/v1/admin/products/{id}/approve
      Backend:
        -> Product.is_approved = TRUE
        -> Product is now visible on all public endpoints
        -> Product appears in search results, category listings
        -> TAX: The product's hsn_code and tax_rule_id are now active.
           When sold, the system will look up tax using:
           product.tax_rule_id -> TaxRule -> TaxCategory (cgst/sgst/igst rates)
           OR (if no product rule) -> category's TaxRule -> TaxCategory
      Response: { message: "Product approved successfully" }

4B. ADMIN REJECTS PRODUCT
    PUT /api/v1/admin/products/{id}/reject
      Body: { reason: "Incorrect pricing / Missing images / Invalid category / Wrong HSN code" }
      Backend:
        -> Product.is_approved = FALSE (stays)
        -> reject_reasons array appended:
           [{ "reason": "...", "rejected_by": admin_id, "rejected_at": timestamp }]
      Response: { message: "Product rejected" }
      -> Dealer sees rejection reason in their product list
      -> Dealer can edit product and re-submit (it stays in pending state)

5. PRODUCT VISIBILITY RULES (after approval)
   Public listing (GET /products, GET /products/search, GET /categories/{id}/products):
     WHERE is_approved = True
       AND dealer.access_status = 'active'
       AND dealer.is_active = True
       AND dealer.is_deleted = False
       AND product.is_deleted = False
       AND (dealer.partner.is_active = True OR dealer.partner_id IS NULL)
   Dealer view: ALL their products (approved + pending + rejected)
   Admin view: ALL products system-wide
```

---

### PHASE 4: CUSTOMER DISCOVERS & PURCHASES PRODUCT

```
1. CUSTOMER BROWSES (Frontend: HomeScreen / SearchScreen)
   As guest or logged-in customer
   GET /products -> Lists approved products
   GET /products/search?q=iphone -> Search with filters
   GET /categories/{id}/products -> Category browsing
   GET /products/{id} -> Product detail with:
     - Images, price, description, attributes
     - Variants (size/color picker)
     - Reviews & ratings
     - Dealer info, delivery estimate

2. CUSTOMER ADDS TO CART (if logged in)
   POST /api/v1/cart
     Body: { product_id, variant_id (optional), quantity, size, variant_attributes }
     Backend:
       a) Check if item with same product + variant + size already in cart
       b) If exists: increment quantity
       c) If new: INSERT CartItem
     Response: Updated cart item

3. CUSTOMER VIEWS CART
   GET /api/v1/cart -> All items with product details, prices, totals

4. CUSTOMER PROCEEDS TO CHECKOUT — TAX CALCULATION HAPPENS HERE
   POST /api/v1/orders
     Body: {
       coupon_code (optional),
       payment_method: "COD" | "ONLINE",
       address_id,
       use_wallet (optional),
       wallet_amount (optional)
     }
     
     Backend does ALL of the following in a single transaction:

     a) VALIDATE CART ITEMS
        - Join CartItem -> Product -> Dealer
        - Filter out items where:
          Dealer.access_status != 'active'
          Dealer.is_active != True
          Product.is_approved != True
        - If any items filtered out -> error: "Seller inactive"
        - If cart empty -> error: "Cart is empty"

     b) STOCK CHECK (per item)
        For each cart item:
          - If variant selected: check variant.stock >= quantity
          - If no variant: check product.stock >= quantity
        -> If insufficient stock -> error with product name

     c) PRICE CALCULATION (per item)
        price = selling_price ?? mrp ?? dealer_price
        line_total = price * quantity

     d) ★ TAX CALCULATION (per item — the core tax logic)
        For EACH cart item, TaxService.calculate_item_tax() runs:

        STEP 1 — FIND TAX RULE (priority order):
          1a: Check if product.tax_rule_id is set
              -> If yes, load that TaxRule
              -> If TaxRule.is_active, use it
          1b: If no product rule, check product.category_id
              -> Search TaxRule WHERE category_id = product.category_id
                 AND is_active = True, ordered by priority DESC
              -> Take the highest priority match
          1c: If no category rule, check product.category.parent_id
              -> Same search on parent category
          1d: If still nothing found -> default 0% tax

        STEP 2 — LOAD TAX RATES:
          From the matched TaxRule -> TaxCategory:
            cgst_rate = 9.0  (e.g., for GST 18% slab)
            sgst_rate = 9.0
            igst_rate = 18.0
          tax_category_id = TaxCategory.id (stored for audit trail)

        STEP 3 — DETERMINE INTRA vs INTER STATE:
          buyer_state = shipping_address.state_rel.state_code
          seller_state = product.dealer.state_code
          is_inter_state = (buyer_state != seller_state)
          
          Example:
            Buyer in Karnataka (state_code = "KA")
            Dealer in Tamil Nadu (state_code = "TN")
            -> is_inter_state = true -> IGST applies

        STEP 4 — CALCULATE TAX (price is INCLUSIVE):
          total_rate = igst_rate if is_inter_state
                     = cgst_rate + sgst_rate if intra-state
          
          gross_value = selling_price * quantity      (e.g., ₹1180 * 1 = ₹1180)
          taxable_amount = gross_value / (1 + total_rate/100)
                        = 1180 / 1.18
                        = ₹1000                       (net taxable value)
          total_tax = gross_value - taxable_amount
                    = 1180 - 1000
                    = ₹180                            (total GST)

        STEP 5 — SPLIT TAX INTO COMPONENTS:
          If inter-state:
            igst_amount = total_tax = ₹180
            cgst_amount = 0
            sgst_amount = 0
          If intra-state:
            cgst_amount = total_tax / 2 = ₹90
            sgst_amount = total_tax / 2 = ₹90
            igst_amount = 0

        STEP 6 — RETURN TAX DATA (per item):
          {
            "tax_category_id": 1,          // FK to TaxCategory table
            "taxable_amount": 1000.00,     // Net value (excludes tax)
            "cgst_rate": 9.0,
            "sgst_rate": 9.0,
            "igst_rate": 0.0,
            "cgst_amount": 90.00,
            "sgst_amount": 90.00,
            "igst_amount": 0.00,
            "total_tax": 180.00,
            "is_inter_state": false        // false = intra-state
          }

        NOTE: If the product had no tax rule configured:
          cgst_rate = 0, sgst_rate = 0, igst_rate = 0
          taxable_amount = gross_value (no tax extracted)
          total_tax = 0

     e) PLATFORM FEE (per item)
        platform_fee = dealer.platform_fee_amount * quantity
        (Flat fee per unit, e.g., ₹5 per item)

     f) DELIVERY CHARGE (per dealer)
        For each unique dealer:
          - dealer.delivery_charge (flat fee, e.g., ₹40)
          - If dealer.free_delivery_above > 0 AND subtotal >= threshold:
            Delivery charge WAIVED
        total_delivery_charge = sum of applicable fees

     g) COUPON VALIDATION (if applied)
        Check: coupon exists, is_active, not expired
        Check: usage_limit not reached
        Check: min_order_value met
        Check: dealer scope (if dealer-specific, cart must have their items)
        Calculate discount:
          - PERCENTAGE: total * (discount_value / 100), capped at max_discount_amount
          - FIXED: min(discount_value, total_amount)
        Increment coupon.current_usage
        Response: discount applied

     h) WALLET DEDUCTION (if opted)
        Check CustomerWallet.available_balance
        Deduct min(wallet_balance, max_payable_amount)
        Create WalletTransaction (DEBIT)

     i) STOCK DEDUCTION
        For each item:
          - Find ProductInventory with highest stock for this product
          - Deduct quantity from that hub's inventory

     j) ★ CREATE SEPARATE ORDERS (one per cart item — tax stored here)
        For each cart item, INSERT Order with:
          - customer_id, order_number (10-digit random)
          - subtotal, discount_amount, wallet_amount_used
          - delivery_charge, platform_fee_amount
          - ★ TAX FIELDS:
            tax_amount = 180.00              (total GST for this order)
            cgst_amount = 90.00             (Central GST portion)
            sgst_amount = 90.00             (State GST portion)
            igst_amount = 0.00              (IGST if inter-state)
            is_inter_state = false          (flag for reporting)
          - coupon_id, coupon_code (if applied)
          - payment_method, shipping_address_id
          - status = ORDER_PLACED

     k) ★ CREATE ORDER ITEM (one per order — tax at item level)
        INSERT OrderItem:
          - order_id, product_id, variant_id, quantity, price
          - status = "order_placed"
          - ★ TAX BREAKDOWN (duplicated at item level for reporting):
            tax_amount = 180.00
            cgst_rate = 9.0, cgst_amount = 90.00
            sgst_rate = 9.0, sgst_amount = 90.00
            igst_rate = 0.0, igst_amount = 0.00
          - tax breakdown at item level

     l) ★ GENERATE INVOICE (per order — tax invoice for GST compliance)
        INSERT OrderInvoice:
          - order_id, dealer_id
          - invoice_number = TaxService.generate_tax_invoice_number()
            Format: "TAX-2026-000042" (yearly sequential)
          - total_amount (includes tax)
          - tax_amount (total GST)
          - invoice_date = now
          This invoice is downloadable as PDF showing:
            - Dealer GST number, name, address
            - Customer billing address
            - Item: HSN code, description, quantity, rate, taxable value
            - CGST @ 9%: ₹90.00
            - SGST @ 9%: ₹90.00
            - Total: ₹1180.00

     m) ★ CREATE TAX LEDGER ENTRY (audit trail — one per order item)
        INSERT TaxLedger:
          - order_id, order_item_id
          - tax_category_id (FK to the TaxCategory used)
          - taxable_amount = 1000.00
          - cgst_amount = 90.00
          - sgst_amount = 90.00
          - igst_amount = 0.00
          - total_tax = 180.00
          - hsn_code (from product)
          - created_at = now
        This is an IMMUTABLE audit record. It cannot be modified later.
        Used for: GST filing, tax reports, finance audits.

     n) REFERRAL COMMISSION (if customer was referred)
        Check CustomerReferralProfile:
          - If referred_by_id exists:
            For each item:
              - commission_rate = product.referral_commission_rate 
                                 ?? category.referral_commission_rate 
                                 ?? 2% (default)
              - commission_amount = item_total * (rate / 100)
              - INSERT ReferralOrderCommission (status = PENDING)
              - INSERT ReferralItemCommission (status = PENDING)

     o) CLEAR CART
        DELETE all CartItems for this customer

     p) SEND NOTIFICATIONS
        - Email: SendOrderConfirmation (background task)
        - In-App: Notification (type=ORDER_PLACED)
        - Commit transaction

   Response: Array of created Order objects with items, invoices, etc.
```

---

### PHASE 5: PAYMENT

```
1. CUSTOMER INITIATES PAYMENT
   POST /api/v1/payments/initiate
     Body: { order_id, payment_method: "UPI" | "CARD" | "NET_BANKING" | "COD" }
     Backend:
       - Find Order (must be PENDING status)
       - Check no existing payment for this order
       - Create Payment record (status = PENDING)
       - Generate mock gateway URL / payment intent
     Response: { payment_id, amount, gateway_url, transaction_id }

2. CUSTOMER COMPLETES PAYMENT (Mock)
   POST /api/v1/payments/{id}/confirm
     Body: { 
       payment_method: "UPI" | "CARD" | "COD",
       upi_id (optional, e.g., "success@upi"),
       card_number (optional, e.g., "4111111111111111")
     }
     Backend:
       - Mock card/UPI validation:
         - 4111111111111111 (Visa) -> success
         - 4000000000000002 (Visa) -> declined
         - success@upi -> success
         - failure@upi -> failed
       - On SUCCESS:
         - Payment.status = SUCCESS
         - Order.status = CONFIRMED (from PENDING)
         - Record transaction_id
       - On FAIL:
         - Payment.status = FAILED
         - Order stays PENDING (can retry)
     Response: Payment status

3. FOR COD ORDERS
   - Payment is created with method="COD", status=PENDING
   - Payment is settled when rider collects cash on delivery
   - Admin manages COD settlement via logistics remittance flow
```

---

### PHASE 6: ORDER FULFILLMENT (Dealer side)

```
1. DEALER SEES NEW ORDERS
   GET /api/v1/dealers/orders
     Shows orders containing this dealer's products
     Filters: status, date range, search

2. DEALER UPDATES ORDER STATUS (as they process)
   PUT /api/v1/dealers/orders/{id}/status
     Body: { status: "confirmed" | "processing" | "packaging" | "packed" }

   The full status pipeline the dealer manages:
   
   ORDER_PLACED  (customer confirmed + payment done)
        │
   CONFIRMED     (dealer acknowledges order)
        │
   PROCESSING    (dealer starts preparing)
        │
   PACKAGING     (item being packed)
        │
   PACKED        (item ready for pickup)
        │
   DISPATCHED    (handed to logistics)
        │
   SHIPPED       (in transit)
        │
   AT_HUB        (arrived at delivery hub)
        │
   OUT_FOR_DELIVERY  (rider picked up)
        │
   DELIVERED     (customer received)

   Each status update triggers:
     - OrderItem.status updated
     - Parent Order.status recalculated (based on all items)
     - In-app notification sent to customer
     - Order status history recorded in AuditLog

3. HUB STAFF INTERVENTION (if hubs are used)
   - Hub staff can see orders assigned to their hub
   - Hub staff can assign orders to specific riders
   - Hub staff update status: AT_HUB -> OUT_FOR_DELIVERY

4. RIDER DELIVERY
   - Rider sees assigned deliveries on RiderDashboard
   - Rider updates: OUT_FOR_DELIVERY -> DELIVERED
    - On DELIVERED:
      - Order.delivered_at timestamp recorded
      - Referral commission status updated: PENDING -> CREDITED
        (Money added to referrer's CustomerWallet)
      - ★ Invoice is finalized. The tax details (CGST ₹90, SGST ₹90) are
        now locked in the OrderInvoice and TaxLedger for GST filing.
        The invoice PDF includes:
          Dealer GSTIN, name, address
          Customer name, shipping address
          HSN code, item description, quantity, rate
          Taxable value: ₹1000.00
          CGST @ 9%: ₹90.00
          SGST @ 9%: ₹90.00
          Total with tax: ₹1180.00
          Invoice number: TAX-2026-000042
```

---

### PHASE 7: ORDER CANCELLATION (Customer initiated)

```
1. CUSTOMER REQUESTS CANCELLATION
   POST /api/v1/orders/{id}/cancel
     Body: { reason: "Changed mind / Found cheaper / Other" }
     
     Backend does:

     a) VALIDATE ORDER
        - Order must belong to this customer
        - Status must be one of:
          PENDING, ORDER_PLACED, CONFIRMED, PROCESSING, PACKAGING, PACKED
        - If already SHIPPED or beyond -> cannot cancel

     b) UPDATE STATUS
        Order.status = CANCELLED
        Order.cancellation_reason = reason
        Order.cancelled_at = now
        All OrderItem.status = CANCELLED

     c) RESTORE STOCK
        For each order item:
          Product.stock += item.quantity

     d) REVERSE COUPON
        If coupon was used:
          Coupon.current_usage -= 1
          Delete CouponUsage record

     e) ★ INITIATE REFUND (full amount including tax)
        If Payment.status == SUCCESS:
          Payment.status = REFUNDED
          Payment.refund_amount = order.total_amount  (includes tax ₹180)
          Payment.refund_reason = "Order cancelled"
          Payment.refunded_at = now
          ★ Note: The full ₹1180 is refunded (₹1000 base + ₹180 tax).
            Tax collected is reversed — no tax is due to the government
            because the transaction never completed.
        If COD: No refund needed

     f) SEND NOTIFICATION
        In-app notification: "Order cancelled"

   Response: { status: "CANCELLED", refund_initiated: true/false }
```

---

### PHASE 8: RETURN & EXCHANGE (Customer initiated after delivery)

```
1. CUSTOMER REQUESTS RETURN (within 7 days of delivery)
   POST /api/v1/orders/{id}/return
     Body: {
       order_item_id,
       reason: "Defective / Wrong item / Not as described / Size issue",
       description (optional),
       images (optional, array of URLs),
       is_exchange: false,
       exchange_variant_id (optional, for exchanges only),
       pickup_date (optional)
     }
     
     Backend does:

     a) VALIDATE
        - Order must be DELIVERED
        - Must be within 7 days of delivered_at
        - No existing return for this order_item
        - Item must belong to this order

     b) CREATE RETURN REQUEST
        INSERT OrderReturn:
          order_id, order_item_id, customer_id
          reason, description, images
          is_exchange, exchange_variant_id
          status = REQUESTED
          hub_id = order_item.hub_id
          logistics_partner_id = order_item.logistics_partner_id

     c) SEND NOTIFICATION
        In-app: "Return request submitted"
        Admin/Dealer alerted of new return request

   Response: { id, status: "REQUESTED", message: "Return request submitted" }

2. REVIEW BY ADMIN OR DEALER
   GET /api/v1/admin/returns
     Admin sees ALL returns with filters (status, date, etc.)
     Shows: customer name, phone, product, reason, images, payment method

   OR for dealers:
   Dealer can only see returns for their own products
   (controlled by backend: order_item.product.dealer_id == current_user.dealer_id)

3. ADMIN/DEALER APPROVES RETURN
   POST /api/v1/admin/returns/{id}/approve
     Body: {
       admin_notes (optional),
       refund_amount (optional, override),
       refund_mode (optional, "original_method" | "UPI" | "BANK"),
       refund_reference (optional, UTR number)
     }

     Backend does:

     a) VALIDATE PERMISSIONS
        - Admin OR Dealer can approve
        - Dealer can only approve own products
        - Return must be in REQUESTED status

     b) UPDATE RETURN STATUS
        status = APPROVED
        approved_by = current_user.id
        approved_at = now
        admin_notes = notes

      c) ★ CALCULATE REFUND AMOUNT (includes tax)
         If refund_amount provided in body: use it
         Else: calculate from order_item.price * quantity
         ★ The refund includes the full price the customer paid:
            taxable_amount (₹1000) + GST (₹180) = ₹1180
            Because the customer paid ₹1180 inclusive of tax.
            On refund: the sale is reversed, so the tax collected
            is also returned to the customer. No GST is due.

      d) HANDLE REFUND BASED ON PAYMENT METHOD
        
        CASE 1: ONLINE PAYMENT (UPI/Card/Net-banking)
          - Set refund_mode = "original_method" (or provided mode)
          - If refund_reference (UTR) provided:
            - Mark refund_initiated = TRUE
            - Payment.status = REFUNDED
            - Payment.refund_amount, refund_reason, refunded_at
          - If no refund_reference yet:
            - Mark refund_initiated = FALSE
            - Admin will provide UTR later via /process-refund

        CASE 2: COD PAYMENT
          - No refund needed (customer paid cash)
          - refund_mode = "none"
          - refund_initiated = FALSE
          - refund_amount = 0

     e) UPDATE ORDER STATUS
        Order.status = RETURNED

     f) HANDLE EXCHANGE (if is_exchange = true)
        
        EXCHANGE FLOW:
        1. Verify new variant/product has stock
        2. Calculate price difference:
           If exchange_price > original_price:
             extra_amount_to_collect = difference
           Else: extra_amount_to_collect = 0
        3. Create REPLACEMENT ORDER:
           - order_number = "EXC-" + random(8 chars)
           - Same customer, same shipping address
           - status = CONFIRMED (auto-confirmed)
           - payment_method = "Exchange"
        4. Create replacement OrderItem:
           - New variant/product, quantity 1
           - status = "packaging" (skip queue)
        5. Link replacement to return:
           - order_return.replacement_order_id = replacement.id
        6. Deduct stock for replacement item

     g) SEND NOTIFICATION
        In-app: "Return approved" / "Exchange initiated"

4. ADMIN RECORDS REFUND UTR (if not provided at approval)
   PUT /api/v1/admin/returns/{id}/process-refund
     Body: {
       refund_mode: "UPI" | "BANK" | "original_method",
       refund_reference: "UTR123456789",
       refund_notes (optional)
     }
     Backend:
       - Find return (must be APPROVED status)
       - Update refund_mode, refund_reference
       - Mark refund_initiated = TRUE
       - Update Payment.status = REFUNDED
       - Payment.refund_amount, refund_reason, refunded_at

5. ADMIN REJECTS RETURN
   POST /api/v1/admin/returns/{id}/reject
     Body: {
       reason: "Item not eligible / Return window expired / etc."
     }
     Backend:
       - status = REJECTED
       - admin_notes = reason
     Response: Return rejected

6. PICKUP & COMPLETION LOGISTICS
   After approval, the return pickup flow:
     REQUESTED -> APPROVED -> OUT_FOR_PICKUP 
     -> PICKED_UP -> RETURN_PICKUP_COMPLETED -> COMPLETED/REFUNDED

   For EXCHANGES:
     APPROVED -> OUT_FOR_PICKUP -> PICKED_UP 
     -> OUT_FOR_SWAP -> SWAP_COMPLETED -> EXCHANGE_COMPLETED
   
   The replacement order (EXC-xxxx) gets processed and delivered
   separately through the normal delivery pipeline.

7. RETURN STATUSES (complete list)
   REQUESTED
   APPROVED
   REJECTED
   OUT_FOR_PICKUP
   OUT_FOR_SWAP
   PICKED_UP
   PICKUP_FAILED
   RETURN_PICKUP_PROCESSING
   RETURN_PICKUP_STARTED
   RETURN_PICKUP_COMPLETED
   SWAP_COMPLETED
   EXCHANGE_COMPLETED
   COMPLETED
   REFUNDED
```

---

### PHASE 9: REFERRAL COMMISSION SETTLEMENT

```
1. When customer places an order (Phase 4 step n):
   - ReferralOrderCommission created with status = PENDING
   - ReferralItemCommission created with status = PENDING

2. When order is DELIVERED (Phase 6 step 4):
   - Background task (core/order_status_logic.py) recalculates
   - Commission status: PENDING -> CREDITED
   - Amount added to referrer's CustomerWallet.available_balance
   - WalletTransaction created (CREDIT type)

3. When order is CANCELLED (Phase 7):
   - Commission status: PENDING -> CANCELLED
   - No wallet credit

COMMISSION RATE HIERARCHY:
   Product-level override -> Category-level rate -> Default 2%
```

---

## Permission Matrix

| Action | Customer | Dealer | Dealer Staff | Admin | Super Admin | Helpdesk |
|--------|----------|--------|-------------|-------|-------------|----------|
| Browse products | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Add to cart | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Place order | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Create product | ❌ | ✅(own) | ❌ | ✅ | ✅ | ❌ |
| Approve product | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| Approve dealer | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| Manage own orders | ❌ | ✅ | ✅(orders role) | ✅ | ✅ | ❌ |
| Manage users | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| View analytics | ❌ | ✅(own) | ❌ | ✅ | ✅ | ❌ |
| Support tickets | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Manage coupons | ❌ | ✅(own) | ❌ | ✅ | ✅ | ❌ |
| Process returns | ❌ | ✅(own) | ❌ | ✅ | ✅ | ❌ |
| Manage logistics | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |

---

## Navigation Tree

```
AppNavigator
├── Main (Customer)    Home, Bill Pay, Auctions, Orders, Profile
├── Auth               Login, Register, DealerLogin, AdminLogin,
│                      RiderLogin, HubLogin, ShowroomLogin, LogisticsLogin
├── DealerStack        Dashboard, Products, Orders, Inventory,
│                      Hubs, Showrooms, Finance, Team, Settings
├── AdminStack         Dashboard, Approvals, Users, Categories,
│                      Brands, Logistics, Tickets, Finance, Partners
├── RiderStack         Dashboard, Earnings, Returns, Exchanges, History
├── HubStack           Dashboard, Orders, Team, Riders, Inventory
├── ShowroomStack      Dashboard, Sales, Inventory, Transfers
└── LogisticsStack     Dashboard, Riders, Orders, COD, Earnings
```

---

## Environment Setup

```
DATABASE_URL=postgresql+asyncpg://postgres:123@localhost:5432/onlineshopappdb
SECRET_KEY=supersecretkey1234567890
ACCESS_TOKEN_EXPIRE_MINUTES=11520
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=manigeminipro11@gmail.com
SENDER_PASSWORD=egqjfjglzkqvbsay
```

## JWT Token
- **Algorithm**: HS256
- **Payload**: `{ sub, role, is_customer, exp }`
- **Expiry**: 11520 minutes (8 days)
- **Password hashing**: Argon2
