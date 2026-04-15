# Copyright (c) 2026, Omnexa and contributors
# License: See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from omnexa_fixed_assets.utils.ias16 import depreciable_amount


class FixedAsset(Document):
	def validate(self):
		self._validate_branch_company_match()
		self._validate_category()
		self._sync_default_accounts_from_category()
		self._sync_depreciation_defaults_from_category()
		self._validate_gl_accounts()
		self._validate_ifrs_cost_and_depreciation()
		self._sync_depreciable_and_carrying_amount()
		self._sync_fully_depreciated_status()

	def after_insert(self):
		if not self.qr_payload:
			self.db_set("qr_payload", self.name, update_modified=False)

	def _validate_branch_company_match(self):
		branch_company = frappe.db.get_value("Branch", self.branch, "company")
		if not branch_company:
			frappe.throw(_("Branch {0} does not exist.").format(self.branch), title=_("Branch"))
		if branch_company != self.company:
			frappe.throw(_("Branch belongs to a different company."), title=_("Branch"))

	def _validate_category(self):
		cat = frappe.db.get_value(
			"Fixed Asset Category",
			self.category,
			["company", "is_group"],
			as_dict=True,
		)
		if not cat:
			frappe.throw(_("Category does not exist."), title=_("Category"))
		if cat.company != self.company:
			frappe.throw(_("Category must belong to the same company."), title=_("Category"))
		if cat.is_group:
			frappe.throw(_("Select a leaf category with GL accounts."), title=_("Category"))

	def _sync_default_accounts_from_category(self):
		cat = frappe.get_cached_doc("Fixed Asset Category", self.category)
		if not self.asset_gl_account and cat.asset_gl_account:
			self.asset_gl_account = cat.asset_gl_account
		if not self.accumulated_depreciation_gl_account and cat.accumulated_depreciation_gl_account:
			self.accumulated_depreciation_gl_account = cat.accumulated_depreciation_gl_account
		if not self.depreciation_expense_gl_account and cat.depreciation_expense_gl_account:
			self.depreciation_expense_gl_account = cat.depreciation_expense_gl_account

	def _sync_depreciation_defaults_from_category(self):
		if not self.category:
			return
		cat = frappe.get_cached_doc("Fixed Asset Category", self.category)
		if cat.is_group:
			return
		if not self.useful_life_months and getattr(cat, "default_useful_life_months", None):
			self.useful_life_months = cat.default_useful_life_months
		if getattr(cat, "default_depreciation_method", None) and (not self.depreciation_method or self.depreciation_method == "None"):
			self.depreciation_method = cat.default_depreciation_method
		method = (self.depreciation_method or "").strip()
		if method == "Declining Balance" and not flt(self.declining_balance_rate_annual):
			if flt(getattr(cat, "default_declining_balance_rate", None)):
				self.declining_balance_rate_annual = cat.default_declining_balance_rate
		if method == "Units of Production" and not self.total_estimated_units:
			if getattr(cat, "default_total_estimated_units", None):
				self.total_estimated_units = cat.default_total_estimated_units

	def _validate_gl_accounts(self):
		for field, label in (
			("asset_gl_account", _("Asset account")),
			("accumulated_depreciation_gl_account", _("Accumulated depreciation")),
			("depreciation_expense_gl_account", _("Depreciation expense")),
		):
			acc = self.get(field)
			if not acc:
				frappe.throw(_("Set {0} on the asset or category.").format(label), title=_("GL"))
			row = frappe.db.get_value(
				"GL Account",
				acc,
				["company", "is_group"],
				as_dict=True,
			)
			if not row or row.company != self.company:
				frappe.throw(_("{0}: invalid account for company.").format(label), title=_("GL"))
			if row.is_group:
				frappe.throw(_("{0}: must be a leaf account.").format(label), title=_("GL"))

	def _validate_ifrs_cost_and_depreciation(self):
		cost = flt(self.acquisition_cost)
		salvage = flt(self.salvage_value)
		if cost > 0 and salvage > cost:
			frappe.throw(_("Residual value cannot exceed acquisition cost."), title=_("IAS 16"))
		method = (self.depreciation_method or "").strip()
		if self.status in ("disposed", "draft"):
			return
		if not cost or self.measurement_model != "Cost Model":
			return
		if method in ("", "None"):
			return
		if method == "Straight Line":
			if not self.useful_life_months or int(self.useful_life_months) < 1:
				frappe.throw(
					_("Useful life in months is required for straight-line depreciation."),
					title=_("IAS 16"),
				)
		if method == "Declining Balance":
			if not flt(self.declining_balance_rate_annual) or flt(self.declining_balance_rate_annual) <= 0:
				frappe.throw(
					_("Set a positive annual rate for declining balance depreciation."),
					title=_("IAS 16"),
				)
		if method == "Units of Production":
			if not self.total_estimated_units or int(self.total_estimated_units) < 1:
				frappe.throw(
					_("Total estimated units is required for units-of-production depreciation."),
					title=_("IAS 16"),
				)
		if self.depreciation_start_date and self.capitalization_date:
			if getdate(self.depreciation_start_date) < getdate(self.capitalization_date):
				frappe.throw(
					_("Depreciation start date cannot be before capitalization date."),
					title=_("IAS 16"),
				)

	def _sync_depreciable_and_carrying_amount(self):
		self.depreciable_amount = depreciable_amount(self.acquisition_cost, self.salvage_value)
		self.net_book_value = flt(self.acquisition_cost) - flt(self.accumulated_depreciation)

	def _sync_fully_depreciated_status(self):
		if self.status == "disposed":
			return
		rem = depreciable_amount(self.acquisition_cost, self.salvage_value) - flt(self.accumulated_depreciation)
		if flt(self.acquisition_cost) > 0 and rem <= 0.005 and self.depreciation_method not in ("", "None"):
			if self.status != "fully_depreciated":
				self.status = "fully_depreciated"
