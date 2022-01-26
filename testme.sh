#!/bin/bash -x
function die
{
	echo $*
	exit 1
}

for i in tmp/*.xls; do
	python3 create_j1939db-json.py -f ${i} -w ${i/.xls/.json} || die
done

while read args; do
	for da in tmp/*.json; do
		for log in tmp/*.log; do
			python3 pretty_j1939.py $args --da-json $da $log > /dev/null || die
			head $log | python3 pretty_j1939.py $args --da-json $da - > /dev/null || die
		done
	done
done <<EOF
--candata --link
--format --real-time
EOF

