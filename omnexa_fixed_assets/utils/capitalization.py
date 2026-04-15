# Copyright (c) 2026, Omnexa and contributors
# License: See license.txt

"""Journal Entry helpers for fixed asset capitalization (separate from inventory)."""

import frappe
from frappe import _
from frappe.utils import flt


def post_capitalization_journal_entry(
	*,
	company: str,
	branch: str | None,
	posting_date,
	debit_account: str,
	credit_account: str,
	amount: float,
	reference: str,
	remarks: str,
) -> str:
	"""Create and submit a balanced Journal Entry: Dr asset, Cr source account. Returns JE name."""
	amt = flt(amount)
	if amt <= 0:
		frappe.throw(_("Amount must be positive."), title=_("Capitalization"))

	je = frappe.new_doc("Journal Entry")
	je.company = company
	je.branch = branch
	je.posting_date = posting_date
	je.reference = reference
	je.remarks = remarks
	je.append("accounts", {"account": debit_account, "debit": amt, "credit": 0})
	je.append("accounts", {"account": credit_account, "debit": 0, "credit": amt})
	je.insert()
	je.submit()
	return je.name


def post_gl_journal(
	*,
	company: str,
	branch: str | None,
	posting_date,
	reference: str,
	remarks: str,
	lines: list[dict],
) -> str:
	"""Balanced journal with arbitrary lines: each item ``account``, ``debit``, ``credit``."""
	je = frappe.new_doc("Journal Entry")
	je.company = company
	je.branch = branch
	je.posting_date = posting_date
	je.reference = reference
	je.remarks = remarks
	for row in lines:
		je.append(
			"accounts",
			{
				"account": row["account"],
				"debit": flt(row.get("debit") or 0),
				"credit": flt(row.get("credit") or 0),
			},
		)
	je.insert()
	je.submit()
	return je.name
