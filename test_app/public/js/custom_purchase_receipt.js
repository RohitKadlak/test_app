
frappe.ui.form.on("Purchase Receipt", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;

        frm.add_custom_button(
            __("Update Rate"),
            () => show_rate_dialog(frm),
            __("Actions")
        );
    }
});

function show_rate_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: __("Update Item Rate"),

        fields: [
            {
                fieldname: "item",
                label: __("Item"),
                fieldtype: "Select",
                options: frm.doc.items.map(row => ({
                    label: `${row.item_code} - ${row.rate}`,
                    value: row.name
                })),
                reqd: 1
            },
            {
                fieldname: "new_rate",
                label: __("New Rate"),
                fieldtype: "Currency",
                reqd: 1
            }
        ],

        primary_action_label: __("Update Rate"),

        primary_action(values) {
            if (values.new_rate <= 0) {
                frappe.msgprint(__("New rate must be greater than zero"));
                return;
            }

            frappe.confirm(
                __("Are you sure you want to update the rate?"),
                () => {
                    // Close dialog after clicking Yes
                    dialog.hide();

                    frappe.call({
                        method: "test_app.public.py.custom_purchase_receipt.change_submitted_purchase_receipt_rate",
                        args: {
                            purchase_receipt: frm.doc.name,
                            item_row_name: values.item,
                            new_rate: values.new_rate
                        },
                        freeze: true,
                        freeze_message: __("Updating rate..."),

                        callback(r) {
                            if (!r.message) return;

                            frappe.msgprint(__("Rate updated successfully"));
                            frm.reload_doc();
                        }
                    });
                }
            );
        }
    });

    dialog.show();
}

