"""Merge pytest JUnit durations into a per-test timing CSV."""

import argparse
import csv
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from test_policy import group_for_nodeid

FIELDS=('nodeid','group','seconds','outcome','measured_at_utc')


def read_timings(path):
    if not path.is_file():return {}
    with path.open(newline='',encoding='utf-8') as source:
        return {row['nodeid']:row for row in csv.DictReader(source)}


def update_timings(rows,junit):
    root=ET.parse(junit).getroot()
    suites=root.findall('.//testsuite')
    if root.tag=='testsuite':suites.insert(0,root)
    measured_at=next((suite.get('timestamp') for suite in suites if suite.get('timestamp')),None)
    measured_at=measured_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    updated=0
    for case in root.findall('.//testcase'):
        classname=case.get('classname','')
        name=case.get('name','')
        if not classname.startswith('tests.') or not name:continue
        if case.find('skipped') is not None:continue
        nodeid='tests/'+classname.removeprefix('tests.').replace('.','/')+'.py::'+name
        outcome='failed' if case.find('failure') is not None or case.find('error') is not None else 'passed'
        rows[nodeid]={
            'nodeid':nodeid,
            'group':group_for_nodeid(nodeid),
            'seconds':f"{float(case.get('time','0')):.3f}",
            'outcome':outcome,
            'measured_at_utc':measured_at,
        }
        updated+=1
    return updated


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('junit',type=Path,help='pytest --junitxml result')
    parser.add_argument('--output',type=Path,default=Path('test-results/timings.csv'))
    parser.add_argument('--seed',type=Path,default=Path('docs/test-timings.csv'))
    parser.add_argument('--prune',action='store_true',help='Remove tests absent from a complete all-enabled report')
    args=parser.parse_args()
    rows=read_timings(args.seed)
    rows.update(read_timings(args.output))
    updated=update_timings(rows,args.junit)
    if args.prune:
        root=ET.parse(args.junit).getroot()
        present={'tests/'+case.get('classname','').removeprefix('tests.').replace('.','/')+'.py::'+case.get('name','')
                 for case in root.findall('.//testcase') if case.get('classname','').startswith('tests.')}
        rows={nodeid:row for nodeid,row in rows.items() if nodeid in present}
    for nodeid,row in rows.items():row['group']=group_for_nodeid(nodeid)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('w',newline='',encoding='utf-8') as target:
        writer=csv.DictWriter(target,fieldnames=FIELDS,lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows,key=lambda key:(rows[key]['group']!='routine',key)))
    print(f'Updated {updated} tests; {len(rows)} measured tests in {args.output}')


if __name__=='__main__':main()
