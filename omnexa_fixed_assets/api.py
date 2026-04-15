# Copyright (c) 2026, Omnexa and contributors
# License: See license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate, today

from omnexa_fixed_assets.utils.ias16 import suggest_monthly_depreciation


@frappe.whitelist()
def run_monthly_depreciation_batch(
	company: str,
	posting_date: str | None = None,
	branch: str | None = None,
	submit_entries: int | str = 1,
	limit: int | str = 500,
):
	"""Create monthly depreciation entries for eligible cost-model assets.

	Idempotency: skip asset if a submitted depreciation entry already exists on `posting_date`.
	Returns a small summary payload for UI/script usage.
	"""
	pd = getdate(posting_date or today())
	submit_flag = cint(submit_entries) == 1
	max_rows = max(1, min(cint(limit), 2000))

	filters = {
		"company": company,
		"measurement_model": "Cost Model",
		"depreciation_method": ["not in", ["", "None"]],
		"status": ["in", ["acquired", "tagged", "in_use", "transferred", "under_maintenance"]],
		"capitalization_journal_entry": ["is", "set"],
	}
	if branch:
		filters["branch"] = branch

	assets = frappe.get_all(
		"Fixed Asset",
		filters=filters,
		fields=[
			"name",
			"company",
			"branch",
			"depreciation_method",
			"acquisition_cost",
			"salvage_value",
			"accumulated_depreciation",
			"useful_life_months",
			"declining_balance_rate_annual",
			"total_estimated_units",
		],
		limit=max_rows,
		order_by="modified asc",
	)

	created: list[str] = []
	submitted: list[str] = []
	skipped: list[dict] = []

	for a in assets:
		exists = frappe.db.exists(
			"Fixed Asset Depreciation Entry",
			{
				"docstatus": 1,
				"fixed_asset": a.name,
				"posting_date": pd,
			},
		)
		if exists:
			skipped.append({"asset": a.name, "reason": "already_posted_on_date"})
			continue

		amount = suggest_monthly_depreciation(
			method=a.depreciation_method or "",
			cost=flt(a.acquisition_cost),
			salvage=flt(a.salvage_value),
			accumulated_depreciation=flt(a.accumulated_depreciation),
			useful_life_months=a.useful_life_months,
			annual_declining_rate_percent=flt(a.declining_balance_rate_annual),
			total_estimated_units=a.total_estimated_units,
			units_this_period=None,
		)
		if amount <= 0:
			skipped.append({"asset": a.name, "reason": "zero_or_no_remaining_depreciation"})
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Fixed Asset Depreciation Entry",
				"naming_series": "FADP-.#####",
				"company": a.company,
				"branch": a.branch,
				"posting_date": pd,
				"fixed_asset": a.name,
				"depreciation_amount": amount,
			}
		)
		doc.insert()
		created.append(doc.name)
		if submit_flag:
			doc.submit()
			submitted.append(doc.name)

	return {
		"posting_date": str(pd),
		"created_count": len(created),
		"submitted_count": len(submitted),
		"skipped_count": len(skipped),
		"created": created,
		"submitted": submitted,
		"skipped": skipped,
	}


@frappe.whitelist()
def run_auto_depreciation_policy_now(policy_name: str, posting_date: str | None = None):
	"""Run one auto-depreciation policy immediately from its form."""
	if not policy_name:
		frappe.throw(_("Policy name is required."))

	policy = frappe.get_doc("Fixed Asset Auto Depreciation Policy", policy_name)
	if not policy.enabled:
		frappe.throw(_("This policy is disabled."), title=_("Auto Depreciation"))

	result = run_monthly_depreciation_batch(
		company=policy.company,
		branch=policy.branch,
		posting_date=posting_date,
		submit_entries=1 if policy.submit_entries else 0,
		limit=policy.max_assets_per_run or 500,
	)
	status = "Success" if result.get("created_count") else "No Data"
	message = (
		f"created={result.get('created_count', 0)}, "
		f"submitted={result.get('submitted_count', 0)}, "
		f"skipped={result.get('skipped_count', 0)}"
	)
	policy.db_set("last_target_posting_date", result.get("posting_date"), update_modified=False)
	policy.db_set("last_run_at", get_datetime(), update_modified=False)
	policy.db_set("last_run_status", status, update_modified=False)
	policy.db_set("last_run_message", message, update_modified=False)
	return result
