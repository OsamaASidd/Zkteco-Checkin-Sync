# Copyright (c) 2025, osama.ahmed@deliverydevs.com
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
import requests
from frappe.utils import today


class ZKTecoConfig(Document):
    pass

@frappe.whitelist()
def register_api_token():
    """
    Calls the remote API to obtain a token and returns it to the client.
    """
    # Fetch from Single DocType
    server_ip = frappe.db.get_single_value("ZKTeco Config", "server_ip")
    server_port = frappe.db.get_single_value("ZKTeco Config", "server_port")
    username = frappe.db.get_single_value("ZKTeco Config", "username")
    password = frappe.db.get_single_value("ZKTeco Config", "password")

    if not all([server_ip, server_port, username, password]):
        frappe.throw(_("Please configure server IP, port, username, and password in ZKTeco Config."))

    # Ensure scheme + port in URL
    url = f"http://{server_ip}:{server_port}/api-token-auth/"

    payload = {
        "username": username,
        "password": password
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        token = data.get("token")
        if not token:
            frappe.throw(_("Token not found in API response."))

        return {"success": True, "token": token}

    except requests.exceptions.RequestException as e:
        frappe.throw(_("Connection error: {0}").format(str(e)))




@frappe.whitelist()
def test_connection():
    """
    Calls:
      http://Server IP :Server Port/iclock/api/transactions/?start_time=YYYY-MM-DD 00:00:00&end_time=YYYY-MM-DD 23:00:00
    Headers:
      Content-Type: application/json
      Authorization: Bearer <token from ZKTeco Config .token>
    """
    # Get token from the singleton config
    cfg = frappe.get_single("ZKTeco Config")
    token = (cfg.token or "").strip()
    server_ip = frappe.db.get_single_value("ZKTeco Config", "server_ip")
    server_port = frappe.db.get_single_value("ZKTeco Config", "server_port")
    if not token:
        return {"ok": False, "error": _("Token not set in ZKTeco Config. Please register/save a token first.")}

    base_url = f"http://{server_ip}:{server_port}/iclock/api/transactions/"
    day = today() # '2021-05-25' 
    start_time = f"{day} 00:00:00"
    end_time   = f"{day} 23:00:00"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    params = {
        "start_time": start_time,
        "end_time": end_time,
    }

    try:
        resp = requests.get(base_url, headers=headers, params=params, timeout=15)
        data_preview = None
        try:
            data = resp.json()
            # Keep response light: preview first item or the object itself
            if isinstance(data, list):
                data_preview = data[:1]
            else:
                data_preview = data
        except Exception:
            data_preview = None

        return {
            "ok": resp.ok,
            "status_code": resp.status_code,
            "url": resp.url,          # shows fully composed URL with encoded params
            "data_preview": data_preview,
        }
    except requests.RequestException as e:
        return {
            "ok": False,
            "error": str(e),
        }