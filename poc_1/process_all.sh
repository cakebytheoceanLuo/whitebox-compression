#!/bin/bash

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
WORKING_DIR="$(pwd)"
repo_wbs_dir=$SCRIPT_DIR/../../public_bi_benchmark-master_project/benchmark
testset_dir=$SCRIPT_DIR/../testsets/testset_unique_schema


usage() {
cat <<EOM
Usage: "$(basename $0)" <wbs-dir>
  wbs-dir    root directory with all the PBIB workbooks
EOM
}

if [ "$#" -lt 1 ]; then
	usage
	exit 1
fi
wbs_dir="$1"


generate_sample() {
	echo "$(date) [generate_sample]"

	wb="$1"
	table="$2"

	sample_file=$wbs_dir/$wb/$table.sample.csv
	if test -f "$sample_file"; then
		echo "debug: skipping sampling; sample already exists"
		return
	fi

	max_sample_size=$((1024*1024*10))
	dataset_nb_rows=$(cat $repo_wbs_dir/$wb/samples/$table.linecount)

	$SCRIPT_DIR/../sampling/main.py --dataset-nb-rows $dataset_nb_rows --max-sample-size $max_sample_size --sample-block-nb-rows 64 --output-file $sample_file $wbs_dir/$wb/$table.csv
}

generate_expression() {
	echo "$(date) [generate_expression]"

	wb="$1"
	table="$2"

	sample_file=$wbs_dir/$wb/$table.sample.csv
	pattern_distr_out_dir=$wbs_dir/$wb/$table.patterns
	ngram_freq_masks_output_dir=$wbs_dir/$wb/$table.ngram_freq_masks
	corr_coefs_output_dir=$wbs_dir/$wb/$table.corr_coefs
	expr_tree_output_dir=$wbs_dir/$wb/$table.expr_tree

	mkdir -p $pattern_distr_out_dir $ngram_freq_masks_output_dir $corr_coefs_output_dir $expr_tree_output_dir

	$SCRIPT_DIR/../pattern_detection/main.py \
	--header-file $repo_wbs_dir/$wb/samples/$table.header-renamed.csv \
	--datatypes-file $repo_wbs_dir/$wb/samples/$table.datatypes.csv \
	--pattern-distribution-output-dir $pattern_distr_out_dir \
	--ngram-freq-masks-output-dir $ngram_freq_masks_output_dir \
	--corr-coefs-output-dir $corr_coefs_output_dir \
	--expr-tree-output-dir $expr_tree_output_dir $sample_file
}

apply_expression() {
	echo "$(date) [apply_expression]"

	wb="$1"
	table="$2"

	input_file=$wbs_dir/$wb/$table.csv
	expr_tree_file=$wbs_dir/$wb/$table.expr_tree/expr_tree.json
	output_dir=$wbs_dir/$wb/$table.poc_1_out
	out_table="${table}_out"

	mkdir -p $output_dir

	time $SCRIPT_DIR/../pattern_detection/apply_expression.py --expr-tree-file $expr_tree_file --header-file $repo_wbs_dir/$wb/samples/$table.header-renamed.csv --datatypes-file $repo_wbs_dir/$wb/samples/$table.datatypes.csv --output-dir $output_dir --out-table-name $out_table $input_file
}


process() {
	echo "$(date) [process]"

	wb="$1"
	table="$2"

	generate_sample $wb $table
	generate_expression $wb $table
	apply_expression $wb $table
}


# https://unix.stackexchange.com/questions/103920/parallelize-a-bash-for-loop
open_sem(){
	mkfifo pipe-$$
	exec 3<>pipe-$$
	rm pipe-$$
	local i=$1
	for((;i>0;i--)); do
		printf %s 000 >&3
	done
}
run_with_lock(){
	local x
	read -u 3 -n 3 x && ((0==x)) || exit $x
	(
		( "$@"; )
		printf '%.3d' $? >&3
	)&
}


nb_procs="$(grep -c ^processor /proc/cpuinfo )"
echo "[parallelism] nb_procs=$nb_procs"

# run in parallel with $nb_procs concurrent tasks
open_sem $nb_procs
for wb in $testset_dir/*; do
	for table in $(cat $wb); do
		wb="$(basename $wb)"
		echo $wb $table

		run_with_lock process $wb $table &> $wbs_dir/$wb/$table.poc_1.process.out
	done
done
wait


: <<'END_COMMENT'
wbs_dir=/scratch/bogdan/tableau-public-bench/data/PublicBIbenchmark-test

================================================================================
./poc_1/process_all.sh $wbs_dir

cat $wbs_dir/*/*.poc_1.process.out | less

END_COMMENT