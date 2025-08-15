// Copyright (c) 2025, osama.ahmed@deliverydevs.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("ZKTeco Config", {
    refresh(frm) {
        
    },

    test_connection(frm) {
    frappe.call({
      method: "zkteco_checkins_sync.zkteco_checkin_sync.doctype.zkteco_config.zkteco_config.test_connection",
      freeze: true,
      freeze_message: __("Testing connection...")
    }).then((r) => {
      const msg = r.message || {};
      if (msg.ok) {
        frappe.show_alert({
          message: __(`✅ Connected. Status ${msg.status_code}. URL: ${msg.url}`),
          indicator: "green"
        });
        // Optional: show a preview of returned data in a dialog
        if (msg.data_preview) {
          frappe.msgprint({
            title: __("Sample Response"),
            message: `<pre style="white-space:pre-wrap">${JSON.stringify(msg.data_preview, null, 2)}</pre>`,
            indicator: "green"
          });
        }
      } else {
        frappe.show_alert({
          message: __(`❌ Failed. Status ${msg.status_code || "N/A"}. URL: ${msg.url || ""}`),
          indicator: "red"
        });
        if (msg.error) {
          frappe.msgprint({
            title: __("Error"),
            message: `<pre style="white-space:pre-wrap">${frappe.utils.escape_html(msg.error)}</pre>`,
            indicator: "red"
          });
        }
      }
    }).catch((e) => {
      frappe.msgprint({
        title: __("Error"),
        message: `<pre style="white-space:pre-wrap">${frappe.utils.escape_html(e.message || e)}</pre>`,
        indicator: "red"
      });
    });
  },


    register_api_token(frm) {
            frappe.call({
                method: "zkteco_checkins_sync.zkteco_checkin_sync.doctype.zkteco_config.zkteco_config.register_api_token",
                freeze: true,
                freeze_message: __("Registering token...")
            }).then((r) => {
                if (r.message && r.message.token) {
                    frm.set_value("token", r.message.token);
                    frm.save().then(() => {
                        frappe.show_alert({ message: __("Token saved."), indicator: "green" });
                    });
                }
            });
        }
});
