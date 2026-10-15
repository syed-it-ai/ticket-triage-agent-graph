"""
Two mock external systems, standing in for a real order database and a
real help-doc index. In production these would be real API calls. Here
they're plain dictionaries so the loop's checks are fully offline and
fully testable, while the *shape* of the check, a real lookup against
a real system, not the model's own claim, is identical to production.
"""

ORDER_DATABASE = {
    "ORD-4471": {"customer": "Priya K.", "amount": 49.99, "status": "delivered"},
    "ORD-8821": {"customer": "Marcus T.", "amount": 612.50, "status": "delivered"},
    "ORD-1203": {"customer": "Wei L.", "amount": 18.00, "status": "shipped"},
}

HELP_DOC_INDEX = {
    "DOC-101": "How to reset your password",
    "DOC-205": "Troubleshooting slow app performance",
    "DOC-310": "Exporting your data to CSV",
    "DOC-412": "Connecting a third-party integration",
}

REFUND_POLICY_MAX_AMOUNT = 500.00
