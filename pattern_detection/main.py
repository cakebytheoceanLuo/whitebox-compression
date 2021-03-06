#!/usr/bin/env python3

import os
import sys
import argparse
import json
import string
from copy import deepcopy
from lib.util import *
from lib.pattern_selectors import *
from patterns import *
from apply_expression import ExpressionManager, apply_expression_manager_list
from lib.expression_tree import ExpressionTree
from plot_expression_tree import plot_expression_tree
from plot_correlation_graph import plot_correlation_graph
import plot_pattern_distribution, plot_ngram_freq_masks, plot_correlation_coefficients
import recursive_exhaustive_learning as rec_exh


# TODO: read this from a config file
iteration_stages = [
{
	"max_it": 16,
	"pattern_detectors": {
		"ConstantPatternDetector": {"min_constant_ratio": 0.9},
		"DictPattern": {"max_dict_size": 64 * 1024, "max_key_ratio": 0.1},
		"NumberAsString": {},
		"CharSetSplit": {
			"default_placeholder": "?",
				"char_sets": [
					{"name": "digits", "placeholder": "D", "char_set": {"0","1","2","3","4","5","6","7","8","9"}},
				],
				"drop_single_char_pattern": True
		}
	},
	"pattern_selector": {
		"type": "PriorityPatternSelector",
		"params": {
			"priorities": [["ConstantPatternDetector"], ["DictPattern"], ["NumberAsString"], ["CharSetSplit"]],
			"coverage_pattern_selector_args": {
				"min_col_coverage": 0.2
			}
		}
	}
},
{
	"max_it": 1,
	"pattern_detectors": {
		"ColumnCorrelation": {"min_corr_coef": 0.9}
	},
	"pattern_selector": {
		"type": "CorrelationPatternSelector",
		"params": {}
	}
}
]
rec_exh_config = {
	"min_col_coverage": 0.2,
	"max_depth": 5
}


class PatternDetectionEngine(object):
	def __init__(self, columns, pattern_detectors):
		self.columns = columns
		self.pattern_detectors = pattern_detectors
		self.total_tuple_count = 0
		self.valid_tuple_count = 0

	def is_valid_tuple(self, tpl):
		if len(tpl) != len(self.columns):
			return False
		return True

	def feed_tuple(self, tpl):
		self.total_tuple_count += 1

		if not self.is_valid_tuple(tpl):
			return False
		self.valid_tuple_count += 1

		for pd in self.pattern_detectors:
			pd.feed_tuple(tpl)

		return True

	def get_patterns(self):
		patterns = {}

		for pd in self.pattern_detectors:
			patterns[pd.name] = {
				"name": pd.name,
				"columns": pd.evaluate()
			}

		return (patterns, self.total_tuple_count, self.valid_tuple_count)


class OutputManager(object):
	@staticmethod
	def output_stats(columns, patterns):
		# for c in columns:
		# 	print(c)
		# print(json.dumps(patterns, indent=2))
		for pd in patterns.values():
			print("*** {} ***".format(pd["name"]))
			for col_id, col_p_list in pd["columns"].items():
				col = next(c for c in columns if c.col_id == col_id)
				print("{}".format(col))
				for p in sorted(col_p_list, key=lambda x: x["coverage"], reverse=True):
					# print("{:.2f}\t{}, res_columns={}, ex_columns={}, operator_info={}".format(p["coverage"], p["p_id"], p["res_columns"], p["ex_columns"], p["operator_info"]))
					# without operator info
					print("{:.2f}\t{}, res_columns={}, ex_columns={}".format(p["coverage"], p["p_id"], p["res_columns"], p["ex_columns"]))
					# debug
					if pd["name"] == "DictPattern":
						print("nb_keys={}".format(len(p["operator_info"]["map"].keys())))
						print("size_keys={}".format(sum([DatatypeAnalyzer.get_value_size(key) for key in p["operator_info"]["map"].keys()])))
					# end-debug

	@staticmethod
	def output_pattern_distribution(stage, level, columns, patterns, pattern_distribution_output_dir, fdelim=",", plot_file_format="svg"):
		# group patterns by columns
		column_patterns = {}
		for c in columns:
			column_patterns[c.col_id] = {}
		for pd in patterns.values():
			for col_id, col_p_list in pd["columns"].items():
				for p in col_p_list:
					column_patterns[col_id][p["p_id"]] = p

		# output pattern distributions
		for col_id, col_p in column_patterns.items():
			if len(col_p.keys()) == 0:
				continue

			out_file = "{}/s_{}_l_{}_col_{}.csv".format(pattern_distribution_output_dir, stage, level, col_id)
			with open(out_file, 'w') as fd:
				# write header
				header = sorted(col_p.keys())
				fd.write(fdelim.join(header) + "\n")

				# write one row at a time
				# TODO: make the implementation easier by using bitmaps instead of row ids
				for p_id in header:
					col_p[p_id]["rows"] = sorted(col_p[p_id]["rows"])

				row_iterators = {p:0 for p in col_p.keys()}
				row_count = 0
				while True:
					current_row = []
					done_cnt = 0
					for p in header:
						rows, r_it = col_p[p]["rows"], row_iterators[p]
						if r_it == len(rows):
							current_row.append("0")
							done_cnt += 1
						elif row_count < rows[r_it]:
							current_row.append("0")
						elif row_count == rows[r_it]:
							row_iterators[p] += 1
							current_row.append("1")
						else:
							raise Exception("Rows are not sorted: col_id={}, p={}, row_count={}, rows[{}]={}".format(col_id, p, row_count, r_it, rows[r_it]))
					if done_cnt == len(header):
						break
					fd.write(fdelim.join(current_row) + "\n")
					row_count += 1

			plot_file="{}/s_{}_l_{}_col_{}.{}".format(pattern_distribution_output_dir, stage, level, col_id, plot_file_format)
			plot_pattern_distribution.main(in_file=out_file, out_file=plot_file, out_file_format=plot_file_format)

	@staticmethod
	def output_ngram_freq_masks(stage, level, ngram_freq_masks, ngram_freq_masks_output_dir, plot_file_format="svg"):
		for col_id, values in ngram_freq_masks.items():
			out_file = "{}/s_{}_l_{}_col_{}.csv".format(ngram_freq_masks_output_dir, stage, level, col_id)
			with open(out_file, 'w') as fd:
				for v in values:
					fd.write(v + "\n")

			plot_file="{}/s_{}_l_{}_col_{}.{}".format(ngram_freq_masks_output_dir, stage, level, col_id, plot_file_format)
			plot_ngram_freq_masks.main(in_file=out_file, out_file=plot_file, out_file_format=plot_file_format)

	@staticmethod
	def output_corr_coefs(stage, level, corr_coefs, corrs, expr_nodes, corr_coefs_output_dir, fdelim=",", plot_file_format="svg"):
		# correlation coefficients
		out_file = "{}/s_{}_l_{}.coefs.csv".format(corr_coefs_output_dir, stage, level)
		columns = sorted(corr_coefs.keys())
		with open(out_file, 'w') as fd:
			header = fdelim.join(columns)
			fd.write(header + "\n")
			for col1_id in columns:
				values = []
				for col2_id in columns:
					values.append("{:.6f}".format(corr_coefs[col1_id][col2_id]))
				fd.write(fdelim.join(values) + "\n")

		plot_file = "{}/s_{}_l_{}.coefs.{}".format(corr_coefs_output_dir, stage, level, plot_file_format)
		plot_correlation_coefficients.main(in_file=out_file, out_file=plot_file, out_file_format=plot_file_format)

		# mark selected corrs
		corrs_res = []
		for corr in corrs:
			src, dst = corr[0], corr[1]
			# check if corr is in the expr_nodes
			for expr_n in expr_nodes:
				if (expr_n.p_name == ColumnCorrelation.get_p_name() and
					src == expr_n.details["src_col_id"] and
					dst == expr_n.cols_in_consumed[0].col_id):
					selected = True
					break
			else:
				selected = False
			corrs_res.append((corr, selected))

		# correlation graph
		out_file = "{}/s_{}_l_{}.graph.json".format(corr_coefs_output_dir, stage, level)
		with open(out_file, 'w') as fd:
			json.dump(corrs_res, fd)
		plot_file = "{}/s_{}_l_{}.graph.svg".format(corr_coefs_output_dir, stage, level)
		plot_correlation_graph(corrs_res, plot_file)

	@staticmethod
	def output_expression_trees(compression_tree, decompression_tree, output_dir, plot=True):
		c_tree_out_file, dec_tree_out_file = os.path.join(output_dir, "c_tree.json"), os.path.join(output_dir, "dec_tree.json")
		with open(c_tree_out_file, 'w') as c_f, open(dec_tree_out_file, 'w') as dec_f:
			json.dump(compression_tree.to_dict(), c_f, indent=2)
			json.dump(decompression_tree.to_dict(), dec_f, indent=2)
		if plot:
			c_tree_plot_file, dec_tree_plot_file = os.path.join(output_dir, "c_tree.svg"), os.path.join(output_dir, "dec_tree.svg")
			plot_expression_tree(compression_tree, c_tree_plot_file,
								 ignore_unused_columns=False)
			plot_expression_tree(decompression_tree, dec_tree_plot_file,
								 ignore_unused_columns=True)


def parse_args():
	parser = argparse.ArgumentParser(
		description="""Detect column patterns in CSV file."""
	)

	parser.add_argument('file', metavar='FILE', nargs='?',
		help='CSV file to process. Stdin if none given')
	parser.add_argument('--header-file', dest='header_file', type=str,
		help="CSV file containing the header row (<workbook>/samples/<table>.header-renamed.csv)",
		required=True)
	parser.add_argument('--datatypes-file', dest='datatypes_file', type=str,
		help="CSV file containing the datatypes row (<workbook>/samples/<table>.datatypes.csv)",
		required=True)
	parser.add_argument('--expr-tree-output-dir', dest='expr_tree_output_dir', type=str,
		help="Output dir to write expression tree data to",
		required=True)
	parser.add_argument('--pattern-distribution-output-dir', dest='pattern_distribution_output_dir', type=str,
		help="Output dir to write pattern distribution to")
	parser.add_argument('--ngram-freq-masks-output-dir', dest='ngram_freq_masks_output_dir', type=str,
		help="Output dir to write ngram frequency masks to")
	parser.add_argument('--corr-coefs-output-dir', dest='corr_coefs_output_dir', type=str,
		help="Output dir to write column correlation coefficients to")
	parser.add_argument("-F", "--fdelim", dest="fdelim",
		help="Use <fdelim> as delimiter between fields", default="|")
	parser.add_argument("--null", dest="null", type=str,
		help="Interprets <NULL> as NULLs", default="null")
	parser.add_argument("--rec-exh", dest="rec_exh", action='store_true',
		help="Use the recursive exhaustive learning algorithm")
	parser.add_argument("--test-sample", dest="test_sample", type=str,
		help="Sample used for estimator test in the recursive exhausting algorithm")
	parser.add_argument('--full-file-linecount', dest='full_file_linecount', type=int,
		help="Number of lines in the full file that the sample was taken from")

	return parser.parse_args()


def read_data(driver, data_manager, fdelim):
	while True:
		line = driver.nextTuple()
		if line is None:
			break
		tpl = line.split(fdelim)
		data_manager.write_tuple(tpl)


def data_loop(data_manager, pd_engine, fdelim):
	data_manager.read_seek_set()
	while True:
		tpl = data_manager.read_tuple()
		if tpl is None:
			break
		pd_engine.feed_tuple(tpl)


def apply_expressions(expr_manager, in_data_manager, out_data_manager):
	total_tuple_count = 0
	valid_tuple_count = 0

	in_data_manager.read_seek_set()
	while True:
		tpl = in_data_manager.read_tuple()
		if tpl is None:
			break
		total_tuple_count += 1

		tpl_new = expr_manager.apply_expressions(tpl)
		if tpl_new is None:
			continue
		valid_tuple_count += 1

		out_data_manager.write_tuple(tpl_new)


def init_pattern_detectors(pattern_detectors, in_columns, pattern_log, expression_tree, null_value):
	pd_instances = []

	for pd_obj_id, (pd_name, pd_params) in enumerate(pattern_detectors.items()):
		class_obj = get_pattern_detector(pd_name)
		pd = class_obj(pd_obj_id, in_columns, pattern_log, expression_tree, null_value,
					   **pd_params)
		pd_instances.append(pd)

	return pd_instances


def init_pattern_selector(pattern_selector):
	class_obj = get_pattern_selector(pattern_selector["type"])
	ps_instance = class_obj(**pattern_selector["params"])

	return ps_instance


def output_iteration_results(args, stage, it, in_columns, pattern_detectors, patterns, expr_nodes):
	# output pattern distributions (for this level)
	if args.pattern_distribution_output_dir is not None:
		OutputManager.output_pattern_distribution(stage, it, in_columns, patterns, args.pattern_distribution_output_dir)

	# output ngram frequency masks (for this level)
	if args.ngram_freq_masks_output_dir is not None:
		ngram_freq_split_pds = [pd for pd in pattern_detectors if isinstance(pd, NGramFreqSplit)]
		if len(ngram_freq_split_pds) > 0:
			if len(ngram_freq_split_pds) != 1:
				print("debug: more that one NGramFreqSplit pattern detector found; using the first one")
			ngram_freq_split = ngram_freq_split_pds[0]
			ngram_freq_masks = ngram_freq_split.get_ngram_freq_masks(delim=",")
			OutputManager.output_ngram_freq_masks(stage, it, ngram_freq_masks, args.ngram_freq_masks_output_dir)
		else:
			print("debug: no NGramFreqSplit pattern detector used")

	# output correlation coefficients (for this level)
	if args.corr_coefs_output_dir is not None:
		col_corr_pds = [pd for pd in pattern_detectors if isinstance(pd, ColumnCorrelation)]
		if len(col_corr_pds) > 0:
			if len(col_corr_pds) != 1:
				print("debug: more that one ColumnCorrelation pattern detector found; using the first one")
			col_corr = col_corr_pds[0]
			corr_coefs, corrs = col_corr.get_corr_coefs()
			if len(corr_coefs.keys()) > 0:
				OutputManager.output_corr_coefs(stage, it, corr_coefs, corrs, expr_nodes, args.corr_coefs_output_dir)
			else:
				print("debug: no columns used in ColumnCorrelation")
		else:
			print("debug: no ColumnCorrelation pattern detector used")


def build_compression_tree_iteration(args, stage, it, in_columns, pattern_detectors, pattern_selector, in_data_manager, expression_tree, pattern_log):
	# init engine
	pd_engine = PatternDetectionEngine(in_columns, pattern_detectors)
	# feed data to engine
	data_loop(in_data_manager, pd_engine, args.fdelim)
	# get results from engine
	(patterns, total_tuple_count, valid_tuple_count) = pd_engine.get_patterns()
	# update pattern log
	pattern_log.update_log(patterns, pattern_detectors)

	# debug
	OutputManager.output_stats(in_columns, patterns)
	# end-debug

	# select patterns for each column
	expr_nodes = pattern_selector.select_patterns(patterns, in_columns, valid_tuple_count)

	# debug
	# for en in expr_nodes: print(en)
	# end-debug

	# output iteration results
	output_iteration_results(args, stage, it, in_columns, pattern_detectors, patterns, expr_nodes)

	# stop if no more patterns can be applied
	if len(expr_nodes) == 0:
		print("stop iteration: no more patterns can be applied")
		return None

	# add expression nodes as a new level in the expression tree
	expression_tree.add_level(expr_nodes)

	# apply expression nodes
	out_data_manager = DataManager()
	expr_manager = ExpressionManager(in_columns, expr_nodes, args.null)
	out_columns = expr_manager.get_out_columns()

	apply_expressions(expr_manager, in_data_manager, out_data_manager)

	# debug
	# for oc in out_columns: print(oc.col_id)
	# for oc in expression_tree.get_out_columns(): print(oc)
	# end-debug

	return (out_columns, out_data_manager)


def build_compression_tree_greedy(args, in_data_manager, columns):
	in_columns = deepcopy(columns)
	expression_tree = ExpressionTree(in_columns, tree_type="compression")
	pattern_log = PatternLog()

	for it_stage_idx, it_stage in enumerate(iteration_stages):
		for it in range(it_stage["max_it"]):
			print("\n\n=== STAGE: {}, ITERATION: it={} ===\n\n".format(it_stage_idx, it))

			# pattern detectors & selector
			pattern_detectors = init_pattern_detectors(it_stage["pattern_detectors"], in_columns, pattern_log, expression_tree, args.null)
			pattern_selector = init_pattern_selector(it_stage["pattern_selector"])

			res = build_compression_tree_iteration(args, it_stage_idx, it,
						in_columns, pattern_detectors, pattern_selector, in_data_manager,
						expression_tree, pattern_log)
			if res is None:
				break
			(out_columns, out_data_manager) = res

			# prepare next iteration
			in_data_manager = out_data_manager
			in_columns = out_columns
		else:
			print("stop iteration: max_it={} reached".format(it_stage["max_it"]))

	return expression_tree

def build_compression_tree_rec_exh(args, in_data_manager, columns):
	# apply recursive exhaustive learning with single-column pattern detectors
	rec_exh_obj = rec_exh.RecursiveExhaustiveLearning(args, in_data_manager, columns,
													  rec_exh_config)
	compression_tree = rec_exh_obj.build_compression_tree()
	
	# apply greedy learning with column correlation
	# apply compression_tree on input data
	expr_manager_list = []
	in_columns = columns
	for idx, level in enumerate(compression_tree.levels):
		expr_nodes = [compression_tree.get_node(node_id) for node_id in level]
		expr_manager = ExpressionManager(in_columns, expr_nodes, args.null)
		expr_manager_list.append(expr_manager)
		# out_columns becomes in_columns for the next level
		in_columns = expr_manager.get_out_columns()
	# data loop
	out_data_manager = DataManager()
	in_data_manager.read_seek_set()
	while True:
		in_tpl = in_data_manager.read_tuple()
		if in_tpl is None:
			break
		out_tpl = apply_expression_manager_list(in_tpl, expr_manager_list)
		out_data_manager.write_tuple(out_tpl)
	# prepare in_data_manager for next stage
	in_data_manager = out_data_manager
	in_data_manager.read_seek_set()

	# apply column correlation
	# pattern detectors & selector
	it_stage = iteration_stages[-1]
	pattern_log = PatternLog()
	pattern_detectors = init_pattern_detectors(it_stage["pattern_detectors"], in_columns, pattern_log, compression_tree, args.null)
	pattern_selector = init_pattern_selector(it_stage["pattern_selector"])
	# build compression tree
	res = build_compression_tree_iteration(args, 1, 0,
				in_columns, pattern_detectors, pattern_selector, in_data_manager,
				compression_tree, pattern_log)
	# (out_columns, out_data_manager) = res
	
	return compression_tree

def build_decompression_tree(c_tree):
	in_columns = [c_tree.get_column(col_id)["col_info"] for col_id in c_tree.get_out_columns()]
	dec_tree = ExpressionTree(in_columns, "decompression")

	# add levels in reverse order
	for level in c_tree.levels[::-1]:
		dec_nodes = []
		for node_id in level:
			c_n = c_tree.nodes[node_id]
			pd = get_pattern_detector(c_n.p_id)
			dec_n = pd.get_decompression_node(c_n)
			dec_nodes.append(dec_n)
		dec_tree.add_level(dec_nodes)

	# validate: c_input_cols should be the same as dec_output_cols
	if set(c_tree.get_in_columns()) != set(dec_tree.get_out_columns()):
		raise Exception("Decompression tree construction failed")

	return dec_tree


def main():
	args = parse_args()
	print(args)

	# read header and datatypes
	with open(args.header_file, 'r') as fd:
		header = list(map(lambda x: x.strip(), fd.readline().split(args.fdelim)))
	with open(args.datatypes_file, 'r') as fd:
		datatypes = list(map(lambda x: DataType.from_sql_str(x.strip()), fd.readline().split(args.fdelim)))
	if len(header) != len(datatypes):
		raise Exception("Header and datatypes do not match")

	# init columns
	columns = []
	for idx, col_name in enumerate(header):
		col_id = str(idx)
		columns.append(Column(col_id, col_name, datatypes[idx]))

	# read data
	in_data_manager = DataManager()
	try:
		if args.file is None:
			fd = os.fdopen(os.dup(sys.stdin.fileno()))
		else:
			fd = open(args.file, 'r')
		f_driver = FileDriver(fd)
		read_data(f_driver, in_data_manager, args.fdelim)
	finally:
		fd.close()

	# build compression tree
	if args.rec_exh:
		print("[algorithm] recursive exhaustive")
		compression_tree = build_compression_tree_rec_exh(args, in_data_manager, columns)
	else:
		print("[algorithm] iterative greedy")
		compression_tree = build_compression_tree_greedy(args, in_data_manager, columns)
	# build decompression tree
	decompression_tree = build_decompression_tree(compression_tree)

	# debug
	print("\n[levels]")
	for idx, level in enumerate(compression_tree.get_node_levels()):
		print("level_{}={}".format(idx+1, level))
		# for node_id in level:
		# 	node = compression_tree.get_node(node_id)
		# 	print("node_id={}, node={}".format(node_id, node))
	# print("[all_columns]")
	# for col_id in compression_tree.columns:
	# 	print(compression_tree.get_column(col_id))
	print("[in_columns]")
	print(compression_tree.get_in_columns())
	print("[out_columns]")
	print(compression_tree.get_out_columns())
	print("[unused_columns]")
	print(compression_tree.get_unused_columns())
	# end-debug

	# output expression trees
	OutputManager.output_expression_trees(compression_tree, decompression_tree, args.expr_tree_output_dir, plot=True)




if __name__ == "__main__":
	main()


"""
#[remote]
wbs_dir=/scratch/bogdan/tableau-public-bench/data/PublicBIbenchmark-test
repo_wbs_dir=/scratch/bogdan/master-project/public_bi_benchmark-master_project/benchmark
#[local-cwi]
wbs_dir=/export/scratch1/bogdan/tableau-public-bench/data/PublicBIbenchmark-poc_1
repo_wbs_dir=/ufs/bogdan/work/master-project/public_bi_benchmark-master_project/benchmark
#[local-personal]
wbs_dir=/media/bogdan/Data/Bogdan/Work/cwi-data/tableau-public-bench/data/PublicBIbenchmark-poc_1
repo_wbs_dir=/media/bogdan/Data/Bogdan/Work/cwi/master-project/public_bi_benchmark-master_project/benchmark

================================================================================
wb=CommonGovernment
table=CommonGovernment_1
max_sample_size=$((1024*1024*10))
================================================================================
wb=Eixo
table=Eixo_1
max_sample_size=$((1024*1024*10))
================================================================================
wb=Arade
table=Arade_1
max_sample_size=$((1024*1024*10))
================================================================================
wb=Generico
table=Generico_2
max_sample_size=$((1024*1024*10))


================================================================================
dataset_nb_rows=$(cat $repo_wbs_dir/$wb/samples/$table.linecount)
pattern_distr_out_dir=$wbs_dir/$wb/$table.patterns
ngram_freq_masks_output_dir=$wbs_dir/$wb/$table.ngram_freq_masks
corr_coefs_output_dir=$wbs_dir/$wb/$table.corr_coefs
expr_tree_output_dir=$wbs_dir/$wb/$table.expr_tree
# uncomment if you want to use the recursive exhaustive algorithm
rec_exh="--rec-exh"
test_sample="--test-sample $wbs_dir/$wb/$table.sample-theoretical-test.csv"
full_file_linecount="--full-file-linecount $(cat $repo_wbs_dir/$wb/samples/$table.linecount)"

#[sample]
./sampling/main.py --dataset-nb-rows $dataset_nb_rows --max-sample-size $max_sample_size --sample-block-nb-rows 64 --output-file $wbs_dir/$wb/$table.sample.csv $wbs_dir/$wb/$table.csv

#[pattern-detection]
mkdir -p $pattern_distr_out_dir $ngram_freq_masks_output_dir $corr_coefs_output_dir $expr_tree_output_dir && \
time ./pattern_detection/main.py --header-file $repo_wbs_dir/$wb/samples/$table.header-renamed.csv \
--datatypes-file $repo_wbs_dir/$wb/samples/$table.datatypes.csv \
--pattern-distribution-output-dir $pattern_distr_out_dir \
--ngram-freq-masks-output-dir $ngram_freq_masks_output_dir \
--corr-coefs-output-dir $corr_coefs_output_dir \
--expr-tree-output-dir $expr_tree_output_dir \
$rec_exh \
$test_sample \
$full_file_linecount \
$wbs_dir/$wb/$table.sample.csv

#[plot-expr-tree]
expr_tree_file=$expr_tree_output_dir/c_tree.json
expr_tree_plot_file=$expr_tree_output_dir/expr_tree_manual.svg
./pattern_detection/plot_expression_tree.py --out-file $expr_tree_plot_file $expr_tree_file

#[scp-pattern-detection-results]
scp -r bogdan@bricks14:/scratch/bogdan/tableau-public-bench/data/PublicBIbenchmark-test/$wb/$table.patterns pattern_detection/output/
scp -r bogdan@bricks14:/scratch/bogdan/tableau-public-bench/data/PublicBIbenchmark-test/$wb/$table.ngram_freq_masks pattern_detection/output/
"""
