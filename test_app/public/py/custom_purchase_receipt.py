
import frappe
from frappe import _
from frappe.utils import flt, money_in_words

@frappe.whitelist()
def change_submitted_purchase_receipt_rate(purchase_receipt, item_row_name, new_rate):

    new_rate = flt(new_rate)

    if new_rate <= 0:
        frappe.throw(_("New rate must be greater than zero"))

    pr = frappe.get_doc("Purchase Receipt", purchase_receipt)

    item = None
    for row in pr.items:
        if row.name == item_row_name:
            item = row
            break

    if not item:
        frappe.throw(_("Purchase Receipt Item not found"))

    if not frappe.db.get_value("Item", item.item_code, "is_stock_item"):
        frappe.throw(_("Item {0} is not a stock item").format(item.item_code))

    sle = frappe.db.get_value(
        "Stock Ledger Entry",
        {
            "voucher_type": "Purchase Receipt",
            "voucher_no": pr.name,
            "voucher_detail_no": item.name,
            "item_code": item.item_code,
            "warehouse": item.warehouse,
            "is_cancelled": 0
        },
        ["name", "actual_qty"],
        as_dict=True
    )

    if not sle:
        frappe.throw(_("Stock Ledger Entry not found"))

    if flt(sle.actual_qty) <= 0:
        frappe.throw(_("Invalid stock quantity"))

    item.rate = new_rate
    pr.flags.ignore_validate_update_after_submit = True
    pr.flags.ignore_validate = True
    pr.calculate_taxes_and_totals()
    pr.in_words = money_in_words(pr.grand_total, pr.currency)
    pr.save(ignore_permissions=True)

    frappe.db.set_value(
        "Stock Ledger Entry",
        sle.name,
        {
            "incoming_rate": new_rate,
            "stock_value_difference": flt(sle.actual_qty) * new_rate
        }
    )

    repost = frappe.new_doc("Repost Item Valuation")

    repost.based_on = "Transaction"
    repost.voucher_type = "Purchase Receipt"
    repost.voucher_no = pr.name
    repost.item_code = item.item_code
    repost.warehouse = item.warehouse
    repost.posting_date = pr.posting_date
    repost.posting_time = pr.posting_time
    repost.company = pr.company

    repost.insert(ignore_permissions=True)
    repost.submit()

