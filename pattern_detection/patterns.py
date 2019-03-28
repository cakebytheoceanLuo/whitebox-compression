import os
import sys
from copy import deepcopy
from lib.util import *
from lib.prefix_tree import PrefixTree


class PatternDetector(object):
	def __init__(self, columns, null_value):
		self.null_value = null_value
		self.row_count = 0
		self.name = self.__class__.__name__

	def feed_tuple(self, tpl):
		self.row_count += 1

	def evaluate(self):
		'''Evaluates the pattern based on the data fed so far

		Returns:
			columns: dict(col_id, patterns) columns analyzed by the pattern detector, where:
				col_id: int # id of the column
				patterns: list(
					dict(
						p_id: # id of the pattern
						score: float # number between 0 and 1 indicating how well the column fits this pattern
						rows: [dict(row_id: int, details: dict() # pattern-specific info), ...], # rows where the pattern applies
						details: dict() # pattern-specific info
					)
				)
		'''
		return dict()

	def is_null(self, attr):
		return attr == self.null_value


class StringPatternDetector(PatternDetector):
	def __init__(self, columns, null_value):
		PatternDetector.__init__(self, columns, null_value)
		self.columns = {}
		for idx, col in enumerate(columns):
			if not col.datatype.startswith("varchar"):
				continue
			self.columns[idx] = {
				"info": deepcopy(col),
				"nulls": [],
				"patterns": {
					"default": {"rows": [], "details": {}},
					#  NOTE: pattern detectors with only one pattern should use the "default" pattern;
					# multi-pattern detectors should add a new entry for each pattern;
					# "default" can be used if there is a main pattern or it can be left empty
				}
			}

	def handle_attr(self, attr, idx):
		'''Handles an attribute

		Returns:
			handled: boolean value indicating whether the attr was handled by this function or not
		'''
		if self.is_null(attr):
			self.columns[idx]["nulls"].append(dict(row_id=self.row_count, details=dict()))
			return True
		return False

	def feed_tuple(self, tpl):
		PatternDetector.feed_tuple(self, tpl)
		for idx in self.columns.keys():
			attr = tpl[idx]
			self.handle_attr(attr, idx)


class NumberAsString(StringPatternDetector):
	def __init__(self, columns, null_value):
		StringPatternDetector.__init__(self, columns, null_value)

	def is_number(self, attr):
		try:
			float(attr)
			return True
		except ValueError as e:
			return False

	def handle_attr(self, attr, idx):
		handled = StringPatternDetector.handle_attr(self, attr, idx)
		if handled:
			return True
		if not self.is_number(attr):
			return True
		self.columns[idx]["patterns"]["default"]["rows"].append(
			dict(row_id=self.row_count, details=dict()))
		return True

	def evaluate(self):
		res = dict()
		for idx, col in self.columns.items():
			if len(col["patterns"]["default"]["rows"]) == 0:
				continue
			# NOTE: treat nulls as valid attrs when computing the score (they will be handled separately)
			score = 0 if self.row_count == 0 else (len(col["patterns"]["default"]["rows"]) + len(col["nulls"])) / self.row_count
			p_item = {
				"p_id": "default",
				"score": score,
				"rows": col["patterns"]["default"]["rows"],
				"details": dict(),
			}
			patterns = [p_item]
			res[col["info"].col_id] = patterns
		return res


class StringCommonPrefix(StringPatternDetector):
	def __init__(self, columns, null_value):
		StringPatternDetector.__init__(self, columns, null_value)
		self.prefix_tree = PrefixTree()

	def handle_attr(self, attr, idx):
		handled = StringPatternDetector.handle_attr(self, attr, idx)
		if handled:
			return True
		self.prefix_tree.insert(attr)
		return True

	def evaluate(self):
		return dict()
		# TODO


class CharSetSplit(StringPatternDetector):
	def __init__(self, columns, null_value, default_placeholder, char_sets, empty_string_pattern="<empty_string>"):
		StringPatternDetector.__init__(self, columns, null_value)
		self.default_placeholder = default_placeholder
		self.char_sets = char_sets
		self.empty_string_pattern = empty_string_pattern

	def get_pattern_string(self, attr):
		pattern_string = []

		for c in attr:
			# look for c in each char set
			for c_set in self.char_sets:
				if c not in c_set["char_set"]:
					continue
				ph = c_set["placeholder"]
				break
			# use the default placeholder if not match
			else:
				ph = self.default_placeholder
			# update pattern string (if necessary)
			if len(pattern_string) == 0 or pattern_string[-1] != ph:
				pattern_string.append(ph)

		if len(pattern_string) == 0:
			return self.empty_string_pattern
		else:
			return "".join(pattern_string)

	def handle_attr(self, attr, idx):
		handled = StringPatternDetector.handle_attr(self, attr, idx)
		if handled:
			return True
		col = self.columns[idx]

		# NOTE: drop leading and trailing whitespace
		# TODO: IMPORTANT: it may be fine to strip whitespace for the original columns; but on subcolumns resulted after a SPLIT operation (or other operations) stripping; take this into consideration
		attr = attr.strip()

		ps = self.get_pattern_string(attr)
		if ps not in col["patterns"]:
			col["patterns"][ps] = {"rows": [], "details": {}}
		col["patterns"][ps]["rows"].append(self.row_count)
		return True

	def evaluate(self):
		res = dict()

		for idx, col in self.columns.items():
			patterns = []
			for ps, ps_data in col["patterns"].items():
				if len(ps_data["rows"]) == 0:
					continue
				# NOTE: treat nulls as valid attrs when computing the score (they will be handled separately)
				score = 0 if self.row_count == 0 else (len(ps_data["rows"]) + len(col["nulls"])) / self.row_count
				p_item = {
					"p_id": ps,
					"score": score,
					"rows": ps_data["rows"],
					"details": dict(),
				}
				patterns.append(p_item)
			res[col["info"].col_id] = patterns

		return res
