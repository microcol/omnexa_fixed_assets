# Copyright (c) 2026, Omnexa and contributors
# License: See license.txt

from __future__ import annotations

import frappe
from frappe.utils import add_months, get_datetime, get_last_day, getdate, nowdate

from omnexa_fixed_assets.api import run_monthly_depreciation_batch


def _resolve_target_posting_date(run_date=None):
	"""Prefer month-end of run month, otherwise previous month-end."""
	rd = getdate(run_date or nowdate())
	if rd == get_last_day(rd):
		return rd
	return get_last_day(add_months(rd, -1))


def run_month_end_depreciation_jobs(posting_date=None):
	"""Scheduled monthly runner for company-specific auto depreciation policies."""
	target_date = getdate(posting_date) if posting_date else _resolve_target_posting_date()
	policies = frappe.get_all(
		"Fixed Asset Auto Depreciation Policy",
		filters={"enabled": 1},
		fields=["name", "company", "branch", "submit_entries", "max_assets_per_run"],
	)

	for p in policies:
		try:
			result = run_monthly_depreciation_batch(
				company=p.company,
				branch=p.branch,
				posting_date=str(target_date),
				submit_entries=1 if p.submit_entries else 0,
				limit=p.max_assets_per_run or 500,
			)
			status = "Success" if result.get("created_count") else "No Data"
			message = (
				f"created={result.get('created_count', 0)}, "
				f"submitted={result.get('submitted_count', 0)}, "
				f"skipped={result.get('skipped_count', 0)}"
			)
			frappe.db.set_value(
				"Fixed Asset Auto Depreciation Policy",
				p.name,
				{
					"last_target_posting_date": str(target_date),
					"last_run_at": get_datetime(),
					"last_run_status": status,
					"last_run_message": message,
				},
				update_modified=False,
			)
		except Exception:
			frappe.log_error(
				title=f"Auto depreciation failed: {p.name}",
				message=frappe.get_traceback(),
			)
			frappe.db.set_value(
				"Fixed Asset Auto Depreciation Policy",
				p.name,
				{
					"last_target_posting_date": str(target_date),
					"last_run_at": get_datetime(),
					"last_run_status": "Failed",
					"last_run_message": "See Error Log for traceback.",
				},
				update_modified=False,
			)
