# Copyright (c) 2025, osama.ahmed@deliverydevs.com
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
import requests
from frappe.utils import today, now_datetime, get_datetime, flt
from datetime import datetime, timedelta
import json


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
    Enhanced test connection that shows latest transactions with detailed info
    """
    # Get token from the singleton config
    cfg = frappe.get_single("ZKTeco Config")
    token = (cfg.token or "").strip()
    server_ip = frappe.db.get_single_value("ZKTeco Config", "server_ip")
    server_port = frappe.db.get_single_value("ZKTeco Config", "server_port")
    
    if not token:
        return {"ok": False, "error": _("Token not set in ZKTeco Config. Please register/save a token first.")}

    base_url = f"http://{server_ip}:{server_port}/iclock/api/transactions/"
    day = today()
    start_time = f"{day} 00:00:00"
    end_time = f"{day} 23:59:59"

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
        
        if resp.ok:
            try:
                data = resp.json()
                
                # Process and format transaction data for display
                formatted_transactions = []
                transaction_count = 0
                
                # Handle ZKTeco API response structure
                if isinstance(data, dict) and 'data' in data:
                    transactions = data['data']
                    transaction_count = data.get('count', len(transactions))
                elif isinstance(data, dict) and 'results' in data:
                    transactions = data['results']
                    transaction_count = len(transactions)
                elif isinstance(data, list):
                    transactions = data
                    transaction_count = len(transactions)
                else:
                    transactions = []
                
                # Format latest 5 transactions for preview
                for transaction in transactions[:5]:
                    try:
                        # Map ZKTeco transaction fields based on actual API response
                        emp_code = transaction.get('emp_code')
                        punch_time = transaction.get('punch_time')
                        punch_state = transaction.get('punch_state')
                        punch_state_display = transaction.get('punch_state_display')
                        device_id = transaction.get('terminal_alias') or transaction.get('terminal_sn')
                        first_name = transaction.get('first_name', '')
                        last_name = transaction.get('last_name', '') or ''
                        verify_type_display = transaction.get('verify_type_display')
                        
                        # Combine first and last name
                        zkteco_name = f"{first_name} {last_name}".strip()
                        
                        # Try to find employee name from ERPNext
                        employee_name = zkteco_name
                        erpnext_employee = None
                        if emp_code:
                            # Try to find employee by employee_id or user_id
                            employee = frappe.db.get_value("Employee", 
                                                         {"employee": emp_code}, 
                                                         ["name", "employee_name"])
                            if not employee:
                                employee = frappe.db.get_value("Employee", 
                                                             {"user_id": emp_code}, 
                                                             ["name", "employee_name"])
                            if employee:
                                erpnext_employee = employee[0] if isinstance(employee, tuple) else employee
                                employee_name = f"{employee[1]} (ERPNext)" if isinstance(employee, tuple) else f"{employee} (ERPNext)"
                        
                        # Determine log type based on punch_state
                        log_type = "IN"
                        if punch_state == "1" or punch_state_display == "Check Out":
                            log_type = "OUT"
                        
                        formatted_transactions.append({
                            "id": transaction.get('id'),
                            "employee_code": emp_code,
                            "employee_name": employee_name,
                            "erpnext_employee": erpnext_employee,
                            "punch_time": punch_time,
                            "log_type": log_type,
                            "punch_state_display": punch_state_display,
                            "device_id": device_id,
                            "verify_method": verify_type_display,
                            "zkteco_name": zkteco_name,
                            "department": transaction.get('department'),
                            "raw_data": transaction
                        })
                    except Exception as e:
                        frappe.log_error(f"Error processing transaction: {e}", "ZKTeco Transaction Processing")
                        continue
                
                return {
                    "ok": True,
                    "status_code": resp.status_code,
                    "url": resp.url,
                    "total_transactions": transaction_count,
                    "transactions_preview": formatted_transactions,
                    "raw_sample": transactions[:2] if transactions else [],
                    "message": f"Found {transaction_count} transactions for {day}"
                }
                
            except json.JSONDecodeError as e:
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "error": f"Invalid JSON response: {str(e)}",
                    "raw_response": resp.text[:500]
                }
        else:
            return {
                "ok": False,
                "status_code": resp.status_code,
                "url": resp.url,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
            }
            
    except requests.RequestException as e:
        return {
            "ok": False,
            "error": f"Connection error: {str(e)}"
        }


def sync_zkteco_transactions():
    """
    Main function to sync ZKTeco transactions with ERPNext Employee Checkin records
    """
    # Check if sync is enabled
    cfg = frappe.get_single("ZKTeco Config")
    if not cfg.enable_sync:
        frappe.log_error("ZKTeco sync is disabled", "ZKTeco Sync")
        return
    
    if not cfg.token:
        frappe.log_error("ZKTeco token not configured", "ZKTeco Sync")
        return
    
    try:
        # Get transactions from last sync or last hour
        last_sync = frappe.db.get_single_value("ZKTeco Config", "last_sync") or (now_datetime() - timedelta(hours=1))
        current_time = now_datetime()
        
        transactions = fetch_zkteco_transactions(cfg, last_sync, current_time)
        
        if transactions:
            processed_count = 0
            error_count = 0
            
            for transaction in transactions:
                try:
                    if create_employee_checkin(transaction):
                        processed_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    error_count += 1
                    frappe.log_error(f"Error creating checkin for transaction {transaction}: {str(e)}", "ZKTeco Sync Error")
            
            # Update last sync time and record count
            total_synced = frappe.db.get_single_value("ZKTeco Config", "total_synced_records") or 0
            frappe.db.set_single_value("ZKTeco Config", "last_sync", current_time)
            frappe.db.set_single_value("ZKTeco Config", "total_synced_records", total_synced + processed_count)
            frappe.db.commit()
            
            frappe.logger().info(f"ZKTeco Sync completed: {processed_count} processed, {error_count} errors")
        
    except Exception as e:
        frappe.log_error(f"ZKTeco sync failed: {str(e)}", "ZKTeco Sync Fatal Error")


def fetch_zkteco_transactions(cfg, start_time, end_time):
    """
    Fetch transactions from ZKTeco device
    """
    server_ip = cfg.server_ip
    server_port = cfg.server_port
    token = cfg.token
    
    base_url = f"http://{server_ip}:{server_port}/iclock/api/transactions/"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    
    params = {
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    try:
        resp = requests.get(base_url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        
        data = resp.json()
        
        # Handle ZKTeco API response format
        if isinstance(data, dict) and 'data' in data:
            return data['data']
        elif isinstance(data, dict) and 'results' in data:
            return data['results']
        elif isinstance(data, list):
            return data
        else:
            return []
            
    except Exception as e:
        frappe.log_error(f"Failed to fetch ZKTeco transactions: {str(e)}", "ZKTeco API Error")
        return []


def create_employee_checkin(transaction):
    """
    Create Employee Checkin record from ZKTeco transaction
    """
    try:
        # Extract transaction data based on ZKTeco API response structure
        emp_code = transaction.get('emp_code')
        punch_time = transaction.get('punch_time')
        punch_state = transaction.get('punch_state')
        device_id = transaction.get('terminal_alias') or transaction.get('terminal_sn')
        transaction_id = transaction.get('id')
        
        if not emp_code or not punch_time:
            frappe.log_error(f"Missing required fields in transaction: {transaction}", "ZKTeco Transaction Error")
            return False
        
        # Find employee
        employee = find_employee_by_code(emp_code)
        if not employee:
            frappe.log_error(f"Employee not found for code: {emp_code}", "ZKTeco Employee Mapping")
            return False
        
        # Convert punch_time to datetime
        if isinstance(punch_time, str):
            punch_datetime = get_datetime(punch_time)
        else:
            punch_datetime = punch_time
        
        # Determine log type based on punch_state
        log_type = "IN"
        if punch_state == "1":  # Based on API response: "1" = Check Out
            log_type = "OUT"
        
        # Check if checkin already exists (use transaction ID for uniqueness)
        existing_checkin = frappe.db.exists("Employee Checkin", {
            "employee": employee,
            "time": punch_datetime,
            "device_id": device_id
        })
        
        if existing_checkin:
            return True  # Already processed
        
        # Also check by transaction ID if we store it
        if transaction_id:
            existing_by_id = frappe.db.get_value("Employee Checkin", 
                                               {"device_id": device_id, "employee": employee}, 
                                               "name", 
                                               {"time": ["between", [punch_datetime - timedelta(seconds=5), punch_datetime + timedelta(seconds=5)]]})
            if existing_by_id:
                return True
        
        # Create Employee Checkin
        checkin = frappe.get_doc({
            "doctype": "Employee Checkin",
            "employee": employee,
            "time": punch_datetime,
            "log_type": log_type,
            "device_id": f"{device_id} (ZKTeco-{transaction_id})" if transaction_id else device_id or "ZKTeco Device",
            "skip_auto_attendance": 0
        })
        
        checkin.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return True
        
    except Exception as e:
        frappe.log_error(f"Error creating Employee Checkin: {str(e)}", "ZKTeco Checkin Creation")
        return False


def find_employee_by_code(emp_code):
    """
    Find employee by various ID fields
    """
    # Try employee field first
    employee = frappe.db.get_value("Employee", {"employee": emp_code}, "name")
    if employee:
        return employee
    
    # Try user_id field
    employee = frappe.db.get_value("Employee", {"user_id": emp_code}, "name")
    if employee:
        return employee
    
    # Try attendance_device_id if it exists
    if frappe.db.has_column("Employee", "attendance_device_id"):
        employee = frappe.db.get_value("Employee", {"attendance_device_id": emp_code}, "name")
        if employee:
            return employee
    
    return None


@frappe.whitelist()
def manual_sync():
    """
    Manual sync trigger for testing
    """
    try:
        sync_zkteco_transactions()
        return {"success": True, "message": "Sync completed successfully"}
    except Exception as e:
        frappe.log_error(f"Manual sync failed: {str(e)}", "ZKTeco Manual Sync")
        return {"success": False, "message": f"Sync failed: {str(e)}"}


def scheduled_sync():
    """
    Scheduled sync function that respects the frequency setting
    """
    try:
        cfg = frappe.get_single("ZKTeco Config")
        if not cfg.enable_sync:
            return
            
        # For frequent syncs (less than 60 seconds), check if we should actually run
        sync_seconds = int(cfg.seconds or 300)
        if sync_seconds < 60:
            last_run = frappe.cache().get_value("zkteco_last_sync_run")
            current_time = now_datetime()
            
            if last_run:
                time_diff = (current_time - get_datetime(last_run)).total_seconds()
                if time_diff < sync_seconds:
                    return  # Not yet time for next sync
            
            # Update last run time
            frappe.cache().set_value("zkteco_last_sync_run", current_time)
        
        sync_zkteco_transactions()
        
    except Exception as e:
        frappe.log_error(f"Scheduled ZKTeco sync failed: {str(e)}", "ZKTeco Scheduled Sync Error")


def cleanup_scheduler_check():
    """
    Cleanup function to ensure scheduler is working properly
    """
    try:
        cfg = frappe.get_single("ZKTeco Config")
        if cfg.enable_sync:
            # Log that the scheduler is active
            frappe.logger().info("ZKTeco scheduler check: Active")
    except Exception as e:
        frappe.log_error(f"ZKTeco scheduler check failed: {str(e)}", "ZKTeco Scheduler Check")


@frappe.whitelist()
def get_sync_status():
    """
    Get current sync status and statistics
    """
    try:
        cfg = frappe.get_single("ZKTeco Config")
        
        # Get last sync time
        last_sync = frappe.db.get_single_value("ZKTeco Config", "last_sync")
        
        # Count recent employee checkins from ZKTeco
        recent_checkins = frappe.db.count("Employee Checkin", {
            "device_id": ["like", "%ZKTeco%"],
            "creation": [">=", frappe.utils.add_days(today(), -1)]
        })
        
        return {
            "enabled": cfg.enable_sync,
            "sync_frequency": cfg.seconds,
            "last_sync": last_sync,
            "recent_checkins_24h": recent_checkins,
            "server_configured": bool(cfg.server_ip and cfg.server_port),
            "token_configured": bool(cfg.token)
        }
        
    except Exception as e:
        return {"error": str(e)}