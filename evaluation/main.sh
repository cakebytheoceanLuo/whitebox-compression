#!/bin/bash

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
WORKING_DIR="$(pwd)"
VW_LOG_FILE="/scratch/bogdan/vectorwise/ingres/files/vectorwise.log"
VW_DATA_FILES_DIR="/scratch/bogdan/vectorwise/ingres/data/vectorwise/pbib/CBM/default"


usage() {
cat <<EOM
Usage: "$(basename $0)" <vw-database-name> <input-file>
  vw-database-name    name of the VectorWise database
  input-file          CSV file to load data from
  schema-file         SQL file with schema
  table-name          name of the table; must be the same with the one in the schema-file
  output-dir          directory to put output files in
EOM
}

if [ "$#" -ne 5 ]; then
	usage
	exit 1
fi
DB_NAME="$1"
INPUT_FILE="$2"
SCHEMA_FILE="$3"
TABLE_NAME="$4"
OUTPUT_DIR="$5"

check_db_connectivity() {
	echo "$(date) [check_db_connectivity]"

	echo "help tm\g" | sql $DB_NAME > /dev/null
	ret=$?
	if [ "$ret" -ne 0 ]; then
		echo "error: unable to connect to database"
		exit $ret
	fi
}

create_table() {
	echo "$(date) [create_table]"

	mkdir -p "$OUTPUT_DIR/load-vectorwise"

	query="$(cat $SCHEMA_FILE)\g"
	echo $query | sql $DB_NAME > "$OUTPUT_DIR/load-vectorwise/$TABLE_NAME.create-table.out" 2> "$OUTPUT_DIR/load-vectorwise/$TABLE_NAME.create-table.err"
	ret=$?
	echo $ret > "$OUTPUT_DIR/load-vectorwise/$TABLE_NAME.create-table.ret"
	if [ "$ret" -ne 0 ]; then
		echo "error: unable to create table"
		exit $ret
	fi
}

load_data() {
	echo "$(date) [load_data]"

	echo -n "" > $VW_LOG_FILE
	sleep 2
	echo "$(date) load start for table: $TABLE_NAME" >> $VW_LOG_FILE

	vwload --fdelim "|" --nullvalue "null" --log "$OUTPUT_DIR/load-vectorwise/$TABLE_NAME.load.log" -z --table "$TABLE_NAME" pbib "$INPUT_FILE" > "$OUTPUT_DIR/load-vectorwise/$TABLE_NAME.load.out" 2> "$OUTPUT_DIR/load-vectorwise/$TABLE_NAME.load.err"
	ret=$?
	echo $ret > "$OUTPUT_DIR/load-vectorwise/$TABLE_NAME.load.ret"
	if [ "$ret" -ne 0 ]; then
		echo "error: unable to load data"
		exit $ret
	fi

	sleep 2
	echo "$(date) load end for table: $TABLE_NAME" >> $VW_LOG_FILE
	sleep 2
	cat $VW_LOG_FILE > "$OUTPUT_DIR/stats-vectorwise/$TABLE_NAME.compression-log.out"
}

process_results() {
	load_start_t=$1; load_end_t=$2
	echo "$(date) [process_results]"

	# get table statistics with statdump
	statdump $DB_NAME -r$TABLE_NAME > "$OUTPUT_DIR/stats-vectorwise/$TABLE_NAME.statdump.out" 2> "$OUTPUT_DIR/stats-vectorwise/$TABLE_NAME.statdump.err"
	echo $ret > "$OUTPUT_DIR/stats-vectorwise/$TABLE_NAME.statdump.ret"
	if [ "$ret" -ne 0 ]; then
		echo "error: statdump"
		exit $ret
	fi

	# get list of data files
	find $VW_DATA_FILES_DIR -type f -iname "*$TABLE_NAME*" -newermt "$load_start_t" -not -newermt "$load_end_t" > "$OUTPUT_DIR/load-vectorwise/$TABLE_NAME.data-files.out" 2> /dev/null

	# process all results and get stats
	$SCRIPT_DIR/get_stats.py --schema-file $SCHEMA_FILE --table-name $TABLE_NAME --output-dir $OUTPUT_DIR
}


echo "$(date) [args] $@"

work_dirs="$OUTPUT_DIR/stats-vectorwise $OUTPUT_DIR/load-vectorwise"
mkdir -p $work_dirs

check_db_connectivity

create_table

load_start_t="$(date)"
load_data
load_end_t="$(date)"

process_results "$load_start_t" "$load_end_t"

echo "$(date) [done]"


: <<'END_COMMENT'
wbs_dir=/scratch/bogdan/tableau-public-bench/data/PublicBIbenchmark-test
repo_wbs_dir=/scratch/bogdan/master-project/public_bi_benchmark-master_project/benchmark

================================================================================
wb=Eixo
table=Eixo_1
================================================================================
wb=Arade
table=Arade_1
================================================================================

db_name=pbib
input_file=$wbs_dir/$wb/$table.csv
schema_file=$repo_wbs_dir/$wb/tables/$table.table.sql
table_name=$table
output_dir=$wbs_dir/$wb/$table.evaluation

mkdir -p $output_dir && \
time ./evaluation/main.sh $db_name $input_file $schema_file $table_name $output_dir

time ./evaluation/get_stats.py --schema-file $schema_file --table-name $table_name --output-dir $output_dir

cat $wbs_dir/$wb/$table.evaluation/stats-vectorwise/$table.statdump.out | less
cat $wbs_dir/$wb/$table.evaluation/stats-vectorwise/$table.compression-log.out | less
cat $wbs_dir/$wb/$table.evaluation/load-vectorwise/$table.data-files.out | less
cat $wbs_dir/$wb/$table.evaluation/$table.eval-vectorwise.json | less
END_COMMENT