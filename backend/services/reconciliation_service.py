"""
Reconciliation Business Logic Service

Ported from the WordPress plugin hotel-cashup-reconciliation.
Handles payment categorization, variance calculation, and report aggregation.
"""
import re
import logging
from datetime import date, datetime
from typing import List, Dict, Optional, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


# ============================================
# PAYMENT CATEGORIZATION
# ============================================

def identify_card_type(transaction: dict) -> str:
    """
    Categorize a Newbook transaction into a card type.

    Ported from PHP: HCR_Newbook_API::identify_card_type()

    Returns: 'cash', 'visa_mc', 'amex', 'bacs', or 'other'
    """
    # Handle both old 'type' field and new 'payment_type' field
    ptype = (transaction.get('payment_type') or transaction.get('type') or '').lower()
    method = (transaction.get('method') or '').lower()
    transaction_method = (transaction.get('payment_transaction_method') or '').lower()
    combined = f"{ptype} {method}"

    # Cash must be identified first
    if 'cash' in combined:
        return 'cash'

    # BACS/Bank transfers
    if any(kw in combined for kw in ['eft', 'bacs', 'bank transfer', 'banktransfer', 'direct debit']):
        return 'bacs'

    # Amex - must be explicitly identified
    if 'amex' in combined or 'american express' in combined:
        return 'amex'

    # Visa/Mastercard - must be explicitly identified
    if any(kw in combined for kw in ['visa', 'mastercard', 'master card', 'mc']):
        return 'visa_mc'

    # For gateway/automated transactions, default to visa_mc (most common card type)
    if transaction_method in ('automated', 'gateway', 'cc_gateway'):
        if any(kw in combined for kw in ['card', 'credit', 'debit']):
            return 'visa_mc'
        # Gateway transactions are almost always card payments
        return 'visa_mc'

    if ptype:
        logger.warning(f"Unidentified payment type: '{ptype}' (method: '{method}', transaction_method: '{transaction_method}')")

    return 'other'


def convert_newbook_amount(amount: float) -> float:
    """
    Convert Newbook amount from accounting perspective to revenue perspective.

    In Newbook: payments are negative, refunds are positive.
    For reconciliation: payments should be positive, refunds negative.
    """
    return -float(amount)


def process_transaction(transaction: dict) -> Optional[dict]:
    """
    Process a single Newbook transaction into a payment record.

    Returns None if the transaction should be skipped.
    """
    item_type = transaction.get('item_type', '')

    # Only process payments, refunds, and voided transactions
    if item_type not in ('payments_raised', 'refunds_raised', 'payments_voided', 'refunds_voided'):
        return None

    # Skip balance transfers (system-generated, always net to zero)
    payment_type = transaction.get('payment_type', '')
    if payment_type == 'balance_transfer':
        return None

    amount = convert_newbook_amount(float(transaction.get('item_amount', 0)))

    return {
        'payment_id': transaction.get('item_id', ''),
        'booking_id': str(transaction.get('booking_id', '')),
        'guest_name': transaction.get('account_for_name', ''),
        'payment_date': transaction.get('item_date', ''),
        'payment_type': payment_type,
        'payment_method': '',
        'transaction_method': transaction.get('payment_transaction_method', 'manual'),
        'card_type': identify_card_type(transaction),
        'amount': amount,
        'tendered': 0,
        'processed_by': '',
        'item_type': item_type
    }


def categorize_payments(raw_transactions: List[dict]) -> List[dict]:
    """
    Process raw Newbook API transactions into categorized payment records.

    Filters out non-payment items and balance transfers, converts amounts,
    and identifies card types.
    """
    payments = []
    for transaction in raw_transactions:
        payment = process_transaction(transaction)
        if payment is not None:
            payments.append(payment)
    return payments


def calculate_payment_totals(payments: List[dict]) -> dict:
    """
    Calculate payment totals by reconciliation category.

    Ported from PHP: HCR_Newbook_API::calculate_payment_totals()

    Categories:
    - cash: Physical cash payments
    - manual_visa_mc: Card machine (PDQ) Visa/MC payments
    - manual_amex: Card machine (PDQ) Amex payments
    - gateway_visa_mc: Online/gateway Visa/MC payments
    - gateway_amex: Online/gateway Amex payments
    - bacs: Bank transfers
    """
    totals = {
        'cash': 0.0,
        'manual_visa_mc': 0.0,
        'manual_amex': 0.0,
        'gateway_visa_mc': 0.0,
        'gateway_amex': 0.0,
        'bacs': 0.0
    }

    for payment in payments:
        amount = float(payment.get('amount', 0))
        transaction_method = (payment.get('transaction_method') or '').lower()
        card_type = payment.get('card_type', '')

        if card_type == 'cash':
            totals['cash'] += amount
        elif card_type == 'bacs':
            totals['bacs'] += amount
        elif transaction_method == 'manual':
            if card_type == 'amex':
                totals['manual_amex'] += amount
            elif card_type == 'visa_mc':
                totals['manual_visa_mc'] += amount
        elif transaction_method in ('automated', 'gateway', 'cc_gateway'):
            if card_type == 'amex':
                totals['gateway_amex'] += amount
            elif card_type == 'visa_mc':
                totals['gateway_visa_mc'] += amount

    # Round all totals to 2 decimal places
    return {k: round(v, 2) for k, v in totals.items()}


# ============================================
# TILL SYSTEM TRANSACTIONS
# ============================================

def parse_till_transactions(raw_transactions: List[dict]) -> dict:
    """
    Parse till system transactions from Newbook transaction data.
    Extracts transactions where method is "manual" and item_description follows:
    "Ticket: {number} - {payment_type}"

    Returns dict grouped by payment type with count and total.
    """
    till_payments = {}
    ticket_pattern = re.compile(r'^Ticket:\s*(\d+)\s*-\s*(.+)$', re.IGNORECASE)

    for transaction in raw_transactions:
        item_type = transaction.get('item_type', '')
        if item_type not in ('payments_raised', 'refunds_raised', 'payments_voided', 'refunds_voided'):
            continue

        method = transaction.get('payment_transaction_method', '')
        if method != 'manual':
            continue

        description = transaction.get('item_description', '')
        match = ticket_pattern.match(description)
        if not match:
            continue

        payment_type = match.group(2).strip()

        # Skip balance transfers
        if payment_type == 'balance_transfer':
            continue

        amount = convert_newbook_amount(float(transaction.get('item_amount', 0)))
        if amount == 0:
            continue

        if payment_type not in till_payments:
            till_payments[payment_type] = {
                'payment_type': payment_type,
                'quantity': 0,
                'total': 0.0,
                'transactions': []
            }

        till_payments[payment_type]['quantity'] += 1
        till_payments[payment_type]['total'] += amount
        till_payments[payment_type]['transactions'].append({
            'ticket': match.group(1),
            'amount': amount,
            'item_type': item_type
        })

    # Round totals
    for key in till_payments:
        till_payments[key]['total'] = round(till_payments[key]['total'], 2)

    return till_payments


# ============================================
# VARIANCE CALCULATION
# ============================================

def calculate_variance(banked: float, reported: float) -> float:
    """
    Calculate variance between banked (manual count) and reported (Newbook).

    Positive = over (extra cash/payments found)
    Negative = short (missing cash/payments)
    """
    return round(banked - reported, 2)


def get_variance_status(variance: float, threshold: float = 10.0) -> str:
    """
    Determine variance status for display.

    Returns: 'balanced', 'over', or 'short'
    """
    if abs(variance) <= threshold:
        return 'balanced'
    elif variance > 0:
        return 'over'
    else:
        return 'short'


def build_reconciliation_rows(
    banked_totals: dict,
    reported_totals: dict
) -> List[dict]:
    """
    Build reconciliation comparison rows for each category.

    banked_totals: From manual entry (cash count + card machines)
    reported_totals: From Newbook payments

    Returns list of rows with category, banked, reported, variance.
    """
    categories = [
        ('Cash', 'cash'),
        ('PDQ Visa/MC', 'manual_visa_mc'),
        ('PDQ Amex', 'manual_amex'),
        ('Gateway Visa/MC', 'gateway_visa_mc'),
        ('Gateway Amex', 'gateway_amex'),
        ('BACS', 'bacs'),
    ]

    rows = []
    for label, key in categories:
        banked = banked_totals.get(key, 0.0)
        reported = reported_totals.get(key, 0.0)
        variance = calculate_variance(banked, reported)
        rows.append({
            'category': label,
            'key': key,
            'banked_amount': round(banked, 2),
            'reported_amount': round(reported, 2),
            'variance': variance,
            'status': get_variance_status(variance)
        })

    return rows


# ============================================
# MULTI-DAY REPORT AGGREGATION
# ============================================

def build_multi_day_report(
    cash_ups: List[dict],
    payment_totals_by_date: Dict[str, dict],
    daily_stats: List[dict],
    sales_breakdown: List[dict],
) -> dict:
    """
    Build multi-day report with 3 tables:
    1. Daily Reconciliation Summary (banked vs reported by category per day)
    2. Sales Breakdown (GL categories vs days)
    3. Occupancy Stats (rooms, people, rates per day)

    Returns dict with three table datasets.
    """
    # Table 1: Daily Reconciliation Summary
    recon_summary = []
    total_banked = {
        'cash': 0, 'manual_visa_mc': 0, 'manual_amex': 0,
        'gateway_visa_mc': 0, 'gateway_amex': 0, 'bacs': 0
    }
    total_reported = {
        'cash': 0, 'manual_visa_mc': 0, 'manual_amex': 0,
        'gateway_visa_mc': 0, 'gateway_amex': 0, 'bacs': 0
    }

    for cash_up in cash_ups:
        date_str = cash_up['session_date']
        reported = payment_totals_by_date.get(date_str, {})

        # Build banked totals from cash_up data
        banked = {
            'cash': float(cash_up.get('total_cash_counted', 0)),
            'manual_visa_mc': 0.0,
            'manual_amex': 0.0,
            'gateway_visa_mc': 0.0,
            'gateway_amex': 0.0,
            'bacs': 0.0
        }

        # Card machine totals from cash_up
        for card in cash_up.get('card_machines', []):
            machine_name = card.get('machine_name', '').lower()
            banked['manual_visa_mc'] += float(card.get('visa_mc_amount', 0))
            banked['manual_amex'] += float(card.get('amex_amount', 0))

        # Reported amounts from Newbook
        reported_amounts = {
            'cash': float(reported.get('cash', 0)),
            'manual_visa_mc': float(reported.get('manual_visa_mc', 0)),
            'manual_amex': float(reported.get('manual_amex', 0)),
            'gateway_visa_mc': float(reported.get('gateway_visa_mc', 0)),
            'gateway_amex': float(reported.get('gateway_amex', 0)),
            'bacs': float(reported.get('bacs', 0)),
        }

        # Calculate row variances
        row_variance = {}
        for key in banked:
            row_variance[key] = round(banked[key] - reported_amounts[key], 2)
            total_banked[key] += banked[key]
            total_reported[key] += reported_amounts[key]

        recon_summary.append({
            'date': date_str,
            'status': cash_up.get('status', ''),
            'banked': {k: round(v, 2) for k, v in banked.items()},
            'reported': {k: round(v, 2) for k, v in reported_amounts.items()},
            'variance': row_variance,
            'banked_total': round(sum(banked.values()), 2),
            'reported_total': round(sum(reported_amounts.values()), 2),
        })

    # Totals row
    total_variance = {}
    for key in total_banked:
        total_variance[key] = round(total_banked[key] - total_reported[key], 2)

    recon_totals = {
        'banked': {k: round(v, 2) for k, v in total_banked.items()},
        'reported': {k: round(v, 2) for k, v in total_reported.items()},
        'variance': total_variance,
        'banked_total': round(sum(total_banked.values()), 2),
        'reported_total': round(sum(total_reported.values()), 2),
    }

    # Table 2: Sales Breakdown
    sales_by_date = {}
    all_categories = set()
    for row in sales_breakdown:
        d = row['business_date']
        cat = row['category']
        amt = float(row['net_amount'])
        all_categories.add(cat)
        if d not in sales_by_date:
            sales_by_date[d] = {}
        sales_by_date[d][cat] = amt

    # Table 3: Occupancy Stats
    occupancy_data = []
    for stat in daily_stats:
        occupancy_data.append({
            'date': stat['business_date'],
            'gross_sales': float(stat.get('gross_sales', 0)),
            'rooms_sold': int(stat.get('rooms_sold', 0)),
            'total_people': int(stat.get('total_people', 0)),
            'debtors_creditors': float(stat.get('debtors_creditors_balance', 0)),
        })

    return {
        'reconciliation_summary': {
            'rows': recon_summary,
            'totals': recon_totals,
        },
        'sales_breakdown': {
            'categories': sorted(list(all_categories)),
            'by_date': sales_by_date,
        },
        'occupancy': {
            'rows': occupancy_data,
        }
    }
