#!/usr/bin/python

from ArincTree import ArincFile, RecordClass
from ArincTree import airport_class, airport_runway_class, airport_approach_class, airport_approach_transition_class, airport_approach_waypoint_class, airport_departure_class, airport_departure_transition_class, airport_departure_waypoint_class, airport_arrival_class, airport_arrival_transition_class, airport_arrival_waypoint_class, heliport_class, heliport_approach_class, heliport_approach_transition_class, heliport_approach_waypoint_class, heliport_departure_class, heliport_departure_transition_class, heliport_departure_waypoint_class, heliport_arrival_class, heliport_arrival_transition_class, heliport_arrival_waypoint_class, vhf_navaid_class, ndb_navaid_class, enroute_waypoint_class, enroute_airway_class, airport_waypoint_class, controlled_airspace_class, restrictive_airspace_class, airport_path_point_class

import time
import sqlite3
import os
import decimal
import argparse


def sqlite_write_table_for_class(cur, klass: RecordClass):
    fields = klass.get_fields()
    name_list_str = ",".join(map(lambda x: x.name, fields))
    table_name = klass.label()
    cur.execute(f"CREATE TABLE {table_name} ({name_list_str})")

    question_mark_str = ",".join(["?"] * len(fields))

    for i in klass.instances().values():
        values = list(map(lambda x: i.get(x.name), fields))
        cur.execute(f"INSERT INTO {table_name} VALUES({question_mark_str})", values)


def write_sqlite(a: ArincFile):
    try:
        os.remove(args.output)
    except (OSError, FileNotFoundError):
        pass

    sqlite3.register_adapter(decimal.Decimal, lambda x: str(x))

    con = sqlite3.connect(args.output)
    cur = con.cursor()
    sqlite_write_table_for_class(cur, airport_class)
    sqlite_write_table_for_class(cur, airport_runway_class)
    sqlite_write_table_for_class(cur, airport_approach_class)
    sqlite_write_table_for_class(cur, airport_approach_transition_class)
    sqlite_write_table_for_class(cur, airport_approach_waypoint_class)
    sqlite_write_table_for_class(cur, airport_departure_class)
    sqlite_write_table_for_class(cur, airport_departure_transition_class)
    sqlite_write_table_for_class(cur, airport_departure_waypoint_class)
    sqlite_write_table_for_class(cur, airport_arrival_class)
    sqlite_write_table_for_class(cur, airport_arrival_transition_class)
    sqlite_write_table_for_class(cur, airport_arrival_waypoint_class)
    sqlite_write_table_for_class(cur, heliport_class)
    sqlite_write_table_for_class(cur, heliport_approach_class)
    sqlite_write_table_for_class(cur, heliport_approach_transition_class)
    sqlite_write_table_for_class(cur, heliport_approach_waypoint_class)
    sqlite_write_table_for_class(cur, heliport_departure_class)
    sqlite_write_table_for_class(cur, heliport_departure_transition_class)
    sqlite_write_table_for_class(cur, heliport_departure_waypoint_class)
    sqlite_write_table_for_class(cur, heliport_arrival_class)
    sqlite_write_table_for_class(cur, heliport_arrival_transition_class)
    sqlite_write_table_for_class(cur, heliport_arrival_waypoint_class)
    sqlite_write_table_for_class(cur, vhf_navaid_class)
    sqlite_write_table_for_class(cur, ndb_navaid_class)
    sqlite_write_table_for_class(cur, enroute_waypoint_class)
    sqlite_write_table_for_class(cur, enroute_airway_class)
    sqlite_write_table_for_class(cur, airport_waypoint_class)
    sqlite_write_table_for_class(cur, controlled_airspace_class)
    sqlite_write_table_for_class(cur, restrictive_airspace_class)
    sqlite_write_table_for_class(cur, airport_path_point_class)
    con.commit()


def main():
    default_sqlite_file = "avdb.sqlite"
    parser = argparse.ArgumentParser(
                        prog='navdata_sql',
                        description='convert FAA navdata in ARINC 424 format to an SQLite database',
    )

    parser.add_argument('--missing', action='store_true', help="display report of data we didn't parse because we don't know how")
    parser.add_argument('--ipython', action='store_true', help="after loading the data into memory, run ipython to explore it")
    parser.add_argument('--output',
                        default=default_sqlite_file,
                        help="SQLite file to export data to (default = {default_sqlite_file})",
                        action='store')
    parser.add_argument('arinc_file', help="The ARINC file to read and process")

    global args
    args = parser.parse_args()

    t1 = time.time()
    a = ArincFile(args.arinc_file)
    write_sqlite(a)
    t2 = time.time()

    print("Load time: {0}".format(t2 - t1))

    if args.missing is True:
        a.get_unknowns()

    if args.ipython is True:
        import IPython
        IPython.embed()


main()
