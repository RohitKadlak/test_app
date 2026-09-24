import frappe
from frappe import _
from frappe.utils import flt, now_datetime


@frappe.whitelist()
def change_submitted_purchase_receipt_rate(
    purchase_receipt,
    item_row_name,
    new_rate,
):
    """
    Change the rate of an already submitted Purchase Receipt
    and trigger ERPNext stock valuation reposting.

    Intended for ERPNext v15.
    """

    # ---------------------------------------------------------
    # 1. Validate inputs
    # ---------------------------------------------------------

    if not purchase_receipt:
        frappe.throw(_("Purchase Receipt is required"))

    if not item_row_name:
        frappe.throw(_("Purchase Receipt Item row is required"))

    new_rate = flt(new_rate)

    if new_rate <= 0:
        frappe.throw(_("New rate must be greater than zero"))

    # ---------------------------------------------------------
    # 2. Load Purchase Receipt
    # ---------------------------------------------------------

    pr = frappe.get_doc("Purchase Receipt", purchase_receipt)

    if pr.docstatus != 1:
        frappe.throw(
            _("Purchase Receipt {0} must be submitted").format(
                purchase_receipt
            )
        )

    # ---------------------------------------------------------
    # 3. Find item row
    # ---------------------------------------------------------

    item = None

    for row in pr.items:
        if row.name == item_row_name:
            item = row
            break

    if not item:
        frappe.throw(
            _("Purchase Receipt Item row {0} was not found").format(
                item_row_name
            )
        )

    if not item.item_code:
        frappe.throw(_("Item Code is required"))

    if not item.warehouse:
        frappe.throw(
            _("Warehouse is required for item {0}").format(
                item.item_code
            )
        )

    # ---------------------------------------------------------
    # 4. Get old rate
    # ---------------------------------------------------------

    old_rate = flt(item.rate)

    if old_rate == new_rate:
        return {
            "success": True,
            "message": _("Rate is already {0}").format(new_rate),
            "purchase_receipt": purchase_receipt,
            "item_code": item.item_code,
            "old_rate": old_rate,
            "new_rate": new_rate,
        }

    # ---------------------------------------------------------
    # 5. Make sure stock item
    # ---------------------------------------------------------

    is_stock_item = frappe.db.get_value(
        "Item",
        item.item_code,
        "is_stock_item",
    )

    if not is_stock_item:
        frappe.throw(
            _("Item {0} is not a stock item").format(
                item.item_code
            )
        )

    # ---------------------------------------------------------
    # 6. Find source Stock Ledger Entry
    # ---------------------------------------------------------

    sle = frappe.db.get_value(
        "Stock Ledger Entry",
        {
            "voucher_type": "Purchase Receipt",
            "voucher_no": pr.name,
            "voucher_detail_no": item.name,
            "item_code": item.item_code,
            "warehouse": item.warehouse,
            "is_cancelled": 0,
        },
        [
            "name",
            "actual_qty",
            "incoming_rate",
            "stock_value_difference",
            "qty_after_transaction",
            "stock_value",
        ],
        as_dict=True,
    )

    # Some configurations may not have voucher_detail_no populated.
    if not sle:
        sle = frappe.db.get_value(
            "Stock Ledger Entry",
            {
                "voucher_type": "Purchase Receipt",
                "voucher_no": pr.name,
                "item_code": item.item_code,
                "warehouse": item.warehouse,
                "is_cancelled": 0,
            },
            [
                "name",
                "actual_qty",
                "incoming_rate",
                "stock_value_difference",
                "qty_after_transaction",
                "stock_value",
            ],
            as_dict=True,
        )

    if not sle:
        frappe.throw(
            _(
                "Stock Ledger Entry not found for Purchase Receipt {0}, "
                "Item {1}, Warehouse {2}"
            ).format(
                pr.name,
                item.item_code,
                item.warehouse,
            )
        )

    # ---------------------------------------------------------
    # 7. Don't allow negative / zero incoming quantity
    # ---------------------------------------------------------

    if flt(sle.actual_qty) <= 0:
        frappe.throw(
            _(
                "The Purchase Receipt Stock Ledger Entry does not "
                "contain incoming stock."
            )
        )

    # ---------------------------------------------------------
    # 8. Calculate new amount
    # ---------------------------------------------------------

    qty = flt(item.qty)

    new_amount = qty * new_rate

    # Preserve old amount for audit
    old_amount = flt(item.amount)

    # ---------------------------------------------------------
    # 9. Update Purchase Receipt Item
    # ---------------------------------------------------------

    frappe.db.set_value(
        "Purchase Receipt Item",
        item.name,
        {
            "rate": new_rate,
            "amount": new_amount,
            "base_rate": new_rate * flt(pr.conversion_rate or 1),
            "base_amount": new_amount * flt(pr.conversion_rate or 1),
        },
        update_modified=False,
    )

    # ---------------------------------------------------------
    # 10. Update parent totals
    # ---------------------------------------------------------

    totals = frappe.db.sql(
        """
        SELECT
            SUM(qty) AS total_qty,
            SUM(amount) AS total_amount,
            SUM(base_amount) AS base_total_amount
        FROM `tabPurchase Receipt Item`
        WHERE parent = %s
        """,
        pr.name,
        as_dict=True,
    )[0]

    frappe.db.set_value(
        "Purchase Receipt",
        pr.name,
        {
            "total_qty": flt(totals.total_qty),
            "total": flt(totals.total_amount),
            "base_total": flt(totals.base_total_amount),
            "net_total": flt(totals.total_amount),
            "base_net_total": flt(totals.base_total_amount),
        },
        update_modified=True,
    )

    # ---------------------------------------------------------
    # 11. Update source Stock Ledger Entry
    # ---------------------------------------------------------

    new_stock_value_difference = (
        flt(sle.actual_qty) * new_rate
    )

    # NOTE:
    # We intentionally update only the SOURCE incoming valuation.
    # Future SLE valuation must be recalculated by ERPNext's
    # repost engine.
    frappe.db.set_value(
        "Stock Ledger Entry",
        sle.name,
        {
            "incoming_rate": new_rate,
            "stock_value_difference": new_stock_value_difference,
        },
        update_modified=True,
    )

    # ---------------------------------------------------------
    # 12. Create Repost Item Valuation
    # ---------------------------------------------------------

    repost = frappe.new_doc("Repost Item Valuation")

    repost.based_on = "Transaction"
    repost.voucher_type = "Purchase Receipt"
    repost.voucher_no = pr.name
    repost.item_code = item.item_code
    repost.warehouse = item.warehouse
    repost.posting_date = pr.posting_date
    repost.posting_time = pr.posting_time
    repost.company = pr.company

    repost.flags.ignore_permissions = True
    repost.flags.ignore_links = True

    repost.insert(ignore_permissions=True)
    repost.submit()

    # ---------------------------------------------------------
    # 13. Create audit record / comment
    # ---------------------------------------------------------

    pr.add_comment(
        "Comment",
        _(
            "Rate changed without cancellation.<br>"
            "Item: {0}<br>"
            "Old Rate: {1}<br>"
            "New Rate: {2}<br>"
            "Old Amount: {3}<br>"
            "New Amount: {4}<br>"
            "Repost Item Valuation: {5}"
        ).format(
            item.item_code,
            old_rate,
            new_rate,
            old_amount,
            new_amount,
            repost.name,
        ),
    )

    # ---------------------------------------------------------
    # 14. Return response
    # ---------------------------------------------------------

    return {
        "success": True,
        "message": _(
            "Rate changed successfully and stock valuation reposting "
            "has been queued."
        ),
        "purchase_receipt": pr.name,
        "item_code": item.item_code,
        "warehouse": item.warehouse,
        "old_rate": old_rate,
        "new_rate": new_rate,
        "old_amount": old_amount,
        "new_amount": new_amount,
        "difference": new_amount - old_amount,
        "stock_ledger_entry": sle.name,
        "repost_item_valuation": repost.name,
    }


