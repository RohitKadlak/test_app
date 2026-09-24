
frappe.ui.form.on("Purchase Receipt", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) {
            return;
        }

        frm.add_custom_button(
            __("Change Item Rate"),
            () => {
                open_rate_change_dialog(frm);
            },
            __("Actions")
        );
    }
});


function open_rate_change_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: __("Change Submitted Purchase Receipt Rate"),
        fields: [
            {
                fieldname: "item",
                label: __("Item"),
                fieldtype: "Select",
                options: frm.doc.items.map(row => {
                    return {
                        label: `${row.item_code} - ${row.rate}`,
                        value: row.name
                    };
                })
            },
            {
                fieldname: "new_rate",
                label: __("New Rate"),
                fieldtype: "Currency",
                reqd: 1
            }
        ],
        primary_action_label: __("Change Rate"),
        primary_action(values) {
            if (!values.item) {
                frappe.msgprint(__("Please select an item"));
                return;
            }

            if (!values.new_rate || values.new_rate <= 0) {
                frappe.msgprint(
                    __("New rate must be greater than zero")
                );
                return;
            }

            frappe.confirm(
                __("Are you sure you want to change the submitted Purchase Receipt rate and repost valuation?"),
                () => {
                    frappe.call({
                        method: "test_app.public.py.custom_purchase_receipt.change_submitted_purchase_receipt_rate",
                        args: {
                            purchase_receipt: frm.doc.name,
                            item_row_name: values.item,
                            new_rate: values.new_rate
                        },
                        freeze: true,
                        freeze_message: __(
                            "Changing rate and creating valuation repost..."
                        ),
                        callback(r) {
                            if (!r.message) {
                                return;
                            }

                            frappe.msgprint({
                                title: __("Success"),
                                indicator: "green",
                                message: `
                                    Rate changed successfully.<br><br>

                                    <b>Old Rate:</b>
                                    ${r.message.old_rate}<br>

                                    <b>New Rate:</b>
                                    ${r.message.new_rate}<br>

                                    <b>Difference:</b>
                                    ${r.message.difference}<br>

                                    <b>Repost:</b>
                                    ${r.message.repost_item_valuation}
                                `
                            });

                            dialog.hide();
                            frm.reload_doc();
                        }
                    });
                }
            );
        }
    });

    dialog.show();
}