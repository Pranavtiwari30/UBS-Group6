import json
import os
import random
import uuid
from datetime import datetime, timedelta

def generate_users(count=100):
    users = []
    for i in range(1, count + 1):
        users.append({
            "user_id": f"U{1000 + i}",
            "name": f"User {i}",
            "email": f"user{i}@example.com",
            "balance": round(random.uniform(100.0, 10000.0), 2),
            "account_status": random.choice(["ACTIVE", "ACTIVE", "ACTIVE", "SUSPENDED", "CLOSED"])
        })
    return users

def generate_payments(users, count=200):
    payments = []
    statuses = ["COMPLETED", "FAILED", "PENDING", "REJECTED"]
    rails = ["ACH", "WIRE", "SWIFT", "SEPA"]
    
    for i in range(1, count + 1):
        user = random.choice(users)
        status = random.choices(statuses, weights=[0.6, 0.2, 0.1, 0.1])[0]
        payment_id = f"PAY{1000 + i}"
        
        payments.append({
            "payment_id": payment_id,
            "user_id": user["user_id"],
            "amount": round(random.uniform(10.0, 5000.0), 2),
            "currency": random.choice(["USD", "EUR", "GBP"]),
            "status": status,
            "beneficiary": f"ACC{random.randint(100, 999)}",
            "client_id": f"C{random.randint(10, 99)}",
            "beneficiary_details": f"Beneficiary Name {i}, Bank {random.randint(1, 5)}",
            "payment_rail": random.choice(rails),
            "exception_code": f"EXC{random.randint(10, 99)}" if status in ["FAILED", "REJECTED"] else None,
            "current_transaction_status": status,
            "client_contact_history": [f"Contacted on {datetime.now().strftime('%Y-%m-%d')}"] if random.random() > 0.5 else [],
            "submitted_timestamp": (datetime.now() - timedelta(days=random.randint(0, 30))).isoformat(),
            "prior_retry_events": [f"Retry at {(datetime.now() - timedelta(hours=random.randint(1, 24))).isoformat()}"] if status == "FAILED" else [],
            "compliance_hold_status": random.choice(["NONE", "PENDING_REVIEW", "CLEARED"]),
            "network_acknowledgements": [f"ACK_{random.randint(1000, 9999)}"]
        })
    return payments

def generate_compliance(users, count=100):
    compliance = []
    selected_users = random.sample(users, min(count, len(users)))
    for user in selected_users:
        compliance.append({
            "user_id": user["user_id"],
            "aml_hold": random.random() > 0.9,
            "sanctions_flag": random.random() > 0.95
        })
    return compliance

def generate_exceptions(users, payments, count=150):
    exceptions = []
    types = ["INSUFFICIENT_FUNDS", "COMPLIANCE_HOLD", "NETWORK_FAILURE", "DUPLICATE_PAYMENT", "INVALID_BENEFICIARY"]
    severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    
    # We want exceptions mostly on failed/rejected payments
    problematic_payments = [p for p in payments if p["status"] in ["FAILED", "REJECTED", "PENDING"]]
    
    for i in range(1, count + 1):
        payment = random.choice(problematic_payments) if problematic_payments else random.choice(payments)
        exc_type = random.choice(types)
        
        exceptions.append({
            "case_id": f"CASE{1000 + i}",
            "payment_id": payment["payment_id"],
            "user_id": payment["user_id"],
            "exception_type": exc_type,
            "description": f"Auto-generated exception for {exc_type.lower()}",
            "severity": random.choice(severities),
            "exception_code": payment["exception_code"],
            "current_transaction_status": payment["current_transaction_status"]
        })
    return exceptions

def main():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    users = generate_users(100)
    payments = generate_payments(users, 200)
    compliance = generate_compliance(users, 100)
    exceptions = generate_exceptions(users, payments, 150)
    
    with open(os.path.join(data_dir, "users.json"), "w") as f:
        json.dump(users, f, indent=2)
    
    with open(os.path.join(data_dir, "payments.json"), "w") as f:
        json.dump(payments, f, indent=2)
        
    with open(os.path.join(data_dir, "compliance.json"), "w") as f:
        json.dump(compliance, f, indent=2)
        
    with open(os.path.join(data_dir, "exceptions.json"), "w") as f:
        json.dump(exceptions, f, indent=2)
        
    print("Mock data generated successfully in data/ directory.")

if __name__ == "__main__":
    main()
