import os
import sys
import re
import regex
import json
from lib.util import sizeof_fmt


def data_file_table_match(table_name, f_table):
	return table_name.lower() == f_table.lower()


def data_file_regex_tokens(col_name, regex_any="(.*?)"):
	def char_type(c):
		if ord(c) < 128 and c.isalnum():
			return 1
		else:
			return 0

	regex_col_name = []

	idx = 0
	# -1 so that will trigger a change at the beginning
	current_char_type = -1
	while idx < len(col_name):
		# new regex group
		c = col_name[idx]
		current_char_type = char_type(c)
		if char_type(c) == 1:
			regex_col_name.append("{}".format(c))
		else:
			regex_col_name.append(regex_any)
		idx += 1
		# go until char type change
		while idx < len(col_name):
			c = col_name[idx]
			# char type change
			if char_type(c) != current_char_type:
				break
			# fill token with char
			if char_type(c) == 1:
				regex_col_name[-1] += c
			# regex_any already added
			else:
				pass
			idx += 1

	return regex_col_name


# def data_file_column_match(schema, f_column):
# 	# NOTE: does not work for truncated column names
# 	# You need something like this:
# 	# https://stackoverflow.com/questions/10032788/partial-regex-matching-in-python-3-2?rq=1
#
# 	fuzzy_matches = []
#
# 	for col_id, col_data in schema.items():
# 		col_name = col_data["col_name"]
# 		regex_col_name = data_file_regex_string(col_name)
#
# 		# strict match with f_column
# 		re_string = r'{}'.format(regex_col_name)
# 		m = re.compile(re_string, re.IGNORECASE).search(f_column)
# 		if m:
# 			return col_id
#
# 		# try fuzzy match if strict match failed
# 		# NOTE: long column names are truncated, so look for the BESTMATCH with deletions
# 		re_string = "(?:" + regex_col_name + "){d}"; re_string = r'{}'.format(re_string)
# 		# print(f_column, re_string)
# 		m = regex.match(re_string, f_column, flags=regex.IGNORECASE|regex.BESTMATCH)
# 		fuzzy_matches.append(m)
#
# 	# if no exact match found, select best fuzzy match
# 	print(fuzzy_matches)
#
# 	return None


# def process_data_files(schema, table_name, m_file):
# 	res = {
# 		"columns": {},
# 		"table": {}
# 	}
# 	regex_basename = re.compile(r'^.*?S(.*?)__(.*)_.*?$')
#
# 	d_files = {}
# 	with open(m_file, 'r') as f:
# 		for df in f:
# 			df = df.strip()
# 			basename = os.path.basename(df)
# 			# parse basename
# 			m = regex_basename.match(basename)
# 			if not m:
# 				print("error: Invalid file format: {}".format(df))
# 				continue
# 			f_table = m.group(1)
# 			f_column = m.group(2)
# 			# table filter
# 			if not data_file_table_match(table_name, f_table):
# 				print("debug: table mismatch for file: {}".format(df))
# 				continue
# 			# check column match
# 			col_id = data_file_column_match(schema, f_column)
# 			if col_id is None:
# 				print("debug: column mismatch for file: {}".format(df))
# 				continue
# 			d_files[col_id] = {
# 				"path": df,
# 				"basename": basename,
# 				"f_table": f_table,
# 				"f_column": f_column
# 			}
#
# 	res["table"]["size_B"] = 0
# 	for col_id, col_data in schema.items():
# 		col_stats = {}
# 		if col_id in d_files:
# 			# column size
# 			d_files[col_id]["size_B"] = os.path.getsize(d_files[col_id]["path"])
# 			d_files[col_id]["size_human_readable"] = sizeof_fmt(d_files[col_id]["size_B"])
# 			col_stats["data_file"] = d_files[col_id]
# 			# table size_B
# 			res["table"]["size_B"] += d_files[col_id]["size_B"]
# 		res["columns"][col_id] = col_stats
#
# 	# table size_human_readable
# 	res["table"]["size_human_readable"] = sizeof_fmt(res["table"]["size_B"])
#
# 	return res


def best_f_column(col_id, f_column_set):
	return min(f_column_set, key=lambda f_column: len(f_column))


def best_col_id(f_column, col_id_set, regex_col_names, regex_any):
	def key_f(col_id):
		length = 0
		for token in regex_col_names[col_id]:
			if token != regex_any:
				length += len(token)
		return length
	return max(col_id_set, key=key_f)


def match_data_files(schema, d_files):
	res = {}
	f_matches, c_matches = {}, {}
	regex_any = "(.*?)"

	d_files_dict = {}
	for df in d_files:
		if df["f_column"] in d_files_dict:
			print("debug: multiple files with same f_column: initial={}, current={}".format(d_files_dict[df["f_column"]], df))
			# TODO: think what to do in this case
			continue
		d_files_dict[df["f_column"]] = df

	regex_col_names = {}
	for col_id, col_data in schema.items():
		col_name = col_data["col_name"]
		regex_col_names[col_id] = data_file_regex_tokens(col_name, regex_any)

	unmatched_d_files, unmatched_cols = set(d_files_dict.keys()), set(schema.keys())
	# try strict match
	for f_column in d_files_dict:
		found_match = False
		for col_id, regex_cn in regex_col_names.items():
			re_string = r'^{}$'.format("".join(regex_cn))
			m = re.compile(re_string, re.IGNORECASE).search(f_column)
			if m:
				if f_column not in f_matches:
					f_matches[f_column] = set()
				f_matches[f_column].add(col_id)
				if col_id not in c_matches:
					c_matches[col_id] = set()
				c_matches[col_id].add(f_column)
				# remove from unmatched lists
				unmatched_cols.discard(col_id)
				unmatched_d_files.discard(f_column)
				found_match = True
		if not found_match:
			print("debug: no strict match for file: {}".format(df["path"]))

	# select reciprocal best matches for every (f_column, col_id) pair
	# NOTE: needed for the case of multiple matches
	for f_column, col_id_set in f_matches.items():
		b_col_id = best_col_id(f_column, col_id_set, regex_col_names, regex_any)
		b_f_column = best_f_column(b_col_id, c_matches[b_col_id])
		if f_column == b_f_column:
			res[b_col_id] = d_files_dict[f_column]
		else:
			print("debug: no reciprocal match for: f_column={}, b_col_id={}, b_f_column={}".format(f_column, b_col_id, b_f_column))
			# TODO: think what to do in this case

	print("unmatched_d_files={}".format(unmatched_d_files))
	print("unmatched_cols={}".format(list(map(lambda c: (c, schema[c]["col_name"]), unmatched_cols))))

	# NOTE: fuzzy regex matching does not work that well, try levenshtein distance instead (or a combination of both)
	# try fuzzy match where strict match failed
	# NOTE: this is because long column names are truncated; look for the BESTMATCH with deletions
	match_pairs = []
	for col_id in unmatched_cols:
		regex_cn = regex_col_names[col_id]
		print(regex_cn)
		for f_column in unmatched_d_files:
			re_string = "(?:^" + "".join(regex_cn) + "){d}"; re_string = r'{}'.format(re_string)
			m = regex.match(re_string, f_column, flags=regex.IGNORECASE|regex.BESTMATCH)
			# TODO: compute score
			print(f_column, m)
			score = m.span()[1] - m.span()[0]
			match_pairs.append((col_id, f_column, score))

	print(match_pairs)
	# select pairs in decreasing oreder of the score
	while len(match_pairs) > 0:
		(col_id, f_column, score) = max(match_pairs, key=lambda p: p[2])
		# add pair to res
		res[col_id] = d_files_dict[f_column]
		# update match_pairs, unmatched_d_files and unmatched_cols
		unmatched_d_files.discard(f_column)
		unmatched_cols.discard(col_id)
		match_pairs = list(filter(lambda x: x[0] != col_id and x[1] != f_column, match_pairs))

	print("still unmatched_d_files={}".format(unmatched_d_files))
	print("still unmatched_cols={}".format(list(map(lambda c: (c, schema[c]["col_name"]), unmatched_cols))))

	print(len(schema.keys()), len(d_files), len(d_files_dict))
	print(len(res.keys()))
	return res


def process_data_files(schema, table_name, m_file):
	res = {
		"columns": {},
		"table": {}
	}
	regex_basename = re.compile(r'^.*?S(.*?)__(.*)_.*?$')

	d_files = []
	with open(m_file, 'r') as f:
		for df in f:
			df = df.strip()
			basename = os.path.basename(df)
			# parse basename
			m = regex_basename.match(basename)
			if not m:
				print("error: Invalid file format: {}".format(df))
				continue
			f_table = m.group(1)
			f_column = m.group(2)
			# table filter
			if not data_file_table_match(table_name, f_table):
				print("debug: table mismatch for file: {}".format(df))
				continue
			d_files.append({
				"path": df,
				"basename": basename,
				"f_table": f_table,
				"f_column": f_column
			})

	d_files = match_data_files(schema, d_files)

	res["table"]["size_B"] = 0
	for col_id, col_data in schema.items():
		col_stats = {}
		if col_id in d_files:
			# column size
			d_files[col_id]["size_B"] = os.path.getsize(d_files[col_id]["path"])
			d_files[col_id]["size_human_readable"] = sizeof_fmt(d_files[col_id]["size_B"])
			col_stats["data_file"] = d_files[col_id]
			# table size_B
			res["table"]["size_B"] += d_files[col_id]["size_B"]
		res["columns"][col_id] = col_stats

	# table size_human_readable
	res["table"]["size_human_readable"] = sizeof_fmt(res["table"]["size_B"])

	return res
