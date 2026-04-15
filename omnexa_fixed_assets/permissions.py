# Copyright (c) 2026, Omnexa and contributors
# License: See license.txt

import frappe

from omnexa_core.omnexa_core.branch_access import enforce_branch_access, get_allowed_branches
from omnexa_core.omnexa_core.user_context import apply_company_branch_defaults


def enforce_branch_access_for_doc(doc, method=None):
	enforce_branch_access(doc)


def populate_company_branch_from_user_context(doc, method=None):
	apply_company_branch_defaults(doc)


def _get_query_for_table(table: str, user=None):
	user = user or frappe.session.user
	allowed = get_allowed_branches(user)
	if allowed is None:
		return ""
	if not allowed:
		return "1=0"
	quoted = ", ".join([frappe.db.escape(v) for v in allowed])
	return f"(`tab{table}`.branch in ({quoted}) or `tab{table}`.branch is null or `tab{table}`.branch = '')"


def _companies_for_allowed_branches(user=None):
	user = user or frappe.session.user
	allowed = get_allowed_branches(user)
	if allowed is None:
		return None
	if not allowed:
		return []
	companies = set()
	for b in allowed:
		c = frappe.db.get_value("Branch", b, "company")
		if c:
			companies.add(c)
	return companies


def fixed_asset_category_query_conditions(user=None):
	companies = _companies_for_allowed_branches(user)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	quoted = ", ".join([frappe.db.escape(c) for c in companies])
	return f"`tabFixed Asset Category`.company in ({quoted})"


def fixed_asset_query_conditions(user=None):
	return _get_query_for_table("Fixed Asset", user)


def fixed_asset_acquisition_query_conditions(user=None):
	return _get_query_for_table("Fixed Asset Acquisition", user)


def fixed_asset_depreciation_entry_query_conditions(user=None):
	return _get_query_for_table("Fixed Asset Depreciation Entry", user)


def fixed_asset_disposal_query_conditions(user=None):
	return _get_query_for_table("Fixed Asset Disposal", user)


def fixed_asset_auto_depreciation_policy_query_conditions(user=None):
	companies = _companies_for_allowed_branches(user)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	quoted = ", ".join([frappe.db.escape(c) for c in companies])
	return f"`tabFixed Asset Auto Depreciation Policy`.company in ({quoted})"
