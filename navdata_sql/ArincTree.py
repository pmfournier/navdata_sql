from decimal import Decimal

approach_code_to_name = {
    "B": "LOC/DME BC",
    "D": "VOR/DME",
    "G": "GPS",
    "I": "ILS",
    "H": "RNP",
    "L": "LOC",
    "N": "NDB",
    "Q": "NDB/DME",
    "P": "GPS",
    "S": "VOR using VOR/DME",
    "R": "RNAV",
    "U": "SDF",
    "V": "VOR",
    "X": "LDA"
}


def lstrip(v, chars):
    n = 0
    size = len(v)
    while v[n] in chars:
        n += 1
        if n == size - 1:
            break
    v = v[n:]

    return v


class Field(object):
    def __init__(self, name, begin, end):
        self.name = name
        self.begin = begin
        self.end = end

    def render_impl(self, text):
        return text[self.begin:self.end]

    def render(self, text):
        try:
            return self.render_impl(text)
        except:
            print(f"Failed to call render on field '{self.name}' whose value was '{text[self.begin:self.end]}'")
            print(f"Whole record: {text}")
            raise


area_code_field = Field("area_code", 1, 4)


class FieldLatLng(Field):
    def render_impl(self, text):
        """Convert lat or lng in deg/min/sec to decimal, or none if there is no valid coordinate"""
        text = text[self.begin:self.end]

        if text[0] == " ":
            return None

        if text[0] == "N" or text[0] == "E":
            mult = 1
        else:
            mult = -1

        if text[0] == "N" or text[0] == "S":
            dec = Decimal(text[1:3]) + Decimal(text[3:5]) / 60 + Decimal(text[5:7]) / (60 * 60) + Decimal(text[7:9]) / (60 * 60 * 100)
        else:
            dec = Decimal(text[1:4]) + Decimal(text[4:6]) / 60 + Decimal(text[6:8]) / (60 * 60) + Decimal(text[8:10]) / (60 * 60 * 100)

        return dec.quantize(Decimal("0.000001")) * mult


class FieldSpacePadded(Field):
    def render_impl(self, text):
        spaces = 0
        while True:
            testidx = self.end - (1 + spaces)
            if testidx < self.begin:
                break
            if text[testidx] != ' ':
                break
            spaces += 1
        return text[self.begin: self.end - spaces]


class FieldZeroPadded(Field):
    def render_impl(self, text):
        try:
            out = super(FieldZeroPadded, self).render_impl(text)
            if out[0] == "-":
                # This returns memory not from the original buf
                return "-" + lstrip(out[1:], ["0"])
            # This returns the memory in place
            return int(lstrip(out, ["0"]))
        except:
            print(f"Failure to extract chars {self.begin} {self.end} from {text}")
            raise


class Record(object):
    def __init__(self, klass, text):
        self.text = text
        self._klass = klass
        self._auxiliary_record = None

    def name(self):
        return self._klass.name(self)

    def __repr__(self):
        vals = ""
        for n, f in self._klass._fields.items():
            vals = vals + ("{0}={1}, ".format(n, f.render(self.text)))
        vals = vals[0:-2]

        if self._auxiliary_record is not None:
            for n, f in self._auxiliary_record._klass._fields.items():
                vals = vals + ("{0}={1}, ".format(n, f.render(self.text)))
        applicable_name = self.name()
        return "{0}[{1}] {{ {2} }}".format(self._klass.label(), applicable_name, vals)

    def get(self, attrib):
        val = self._klass.get(self, attrib)

        if val is not None:
            return val

        # FIXME assert that auxiliary record is not None, rather than checking
        if self._auxiliary_record is not None:
            return self._auxiliary_record._klass.get(self._auxiliary_record, attrib)

        return None

    def add_auxiliary_instance(self, subclass, instance):
        """For this record instance, member of a parent class, register an instance of a child class under its local_name"""
        self._auxiliary_record = instance


class RecordClass(object):
    def __init__(self, label: str, parent: 'RecordClass', value_parents_key_field: str, this_key_field: str, fields: list[Field], name_field, required_auxiliary_record_cls=None):
        """
        A class for types of objects in the ARINC database

        label: a pretty name for this class

        parent: the parent type in the type hierarchy

        value_parents_key_field:
            the value that the parent's key field must take for this type to the the more specialized type
            this field can be None if not applicable

        this_key_field: name of the field in this type which will be used to determine the more specialized type; if not applicable, set to None

        name_field:
            Field name, or tuple of field names, used to get the key to identify the
            object uniquely among all the objects of the same class. For instance, for
            an airport, this could be an airport identifier; it has to be unique among
            all objects of this type regardless of whether they descend from the same parent.
            If None, this class will be considered an auxiliary child of the parent,
            i.e. its fields will be considered to be a part of the parent.
        """

        self._label = label
        self._fields = {}
        self._value = value_parents_key_field

        # value -> count map of unknown values seen for this class' key
        self._unknown_values = {}
        # continuation_no -> count of unused continuation records
        self._unused_continuations = {}

        # A name -> object map of the child classes of this class
        self._child_classes = {}

        self._instances = {}
        if parent is not None:
            parent.add_child(self, value_parents_key_field)
        self._parent = parent

        if self._parent is not None:
            self._fields.update(self._parent._fields)
        for f in fields:
            self.add_field(f)

        if this_key_field is None:
            self._key = None
        else:
            self._key = self.get_field(this_key_field)

        if name_field is not None:
            self._name_field = self.get_field_multi(name_field)
        else:
            self._name_field = None

        self._continuation_record_field = self._fields.get("continuation_record_no")

        self._required_auxiliary_record_cls = required_auxiliary_record_cls

    def __repr__(self) -> None:
        return f"RecordClass ({self.label()})"

    def add_field(self, field):
        self._fields[field.name] = field

    def add_child(self, child, value):
        self._child_classes[value] = child

    def parse(self, parent_inst, text):
        """
        Processes a record, going down into class hierarchy to find the most specialized class,
        and adds the record to the class as an instance.
        """

        # First we create an object of this class
        r = Record(self, text)

        existing_instance = r

        # Currently don't support continuation records
        # If the record has a continuation_record field, make sure it's 0 or 1
        # FIXME: this is a hacky, not well encapsulated way to do this.
        # In the future we want to provide continuation-record-specific field lists
        cont_rec_mem = None
        if self._continuation_record_field is not None:
            cont_rec_mem = self.get_by_field(r, self._continuation_record_field)
        if cont_rec_mem is None:
            pass
        else:
            # Hacky exception handling to use this call as a test
            cont_rec = int(cont_rec_mem)
            # Primary continuation records have number 0 or 1
            if cont_rec > 1:
                self._unused_continuations.setdefault(cont_rec, 0)
                self._unused_continuations[cont_rec] += 1
                # Not interested
                return None

        if self._name_field is None:
            # If class defines no name, but still is a child,
            # then it is an auxiliary child, e.g. a class that just extends the
            # parent. It should have a 1:1 relationship with it. E.g. AirportClass
            # and AirportPrimaryRecordClass.
            if parent_inst is not None:
                parent_inst.add_auxiliary_instance(self, r)

        elif self._name_field is not None:
            global_instance_name = r.name()
            existing_instance = self._instances.setdefault(global_instance_name, existing_instance)
            a1 = base_record_class.get_by_field(existing_instance, area_code_field)
            a2 = base_record_class.get_by_field(r, area_code_field)
            if a1 != a2:
                #print("Area code mismatch between {0} \"{1}\" [{2}] and [{3}]".format(self.label(), global_instance_name, a1, a2))
                pass

        if self._key is None:
            # Now try to find a child class to promote it to
            if len(self._child_classes) == 0:
                return existing_instance

            # This is possible. We could get here even with a none key because having child classes with a None key is defined
            # In that case the behavior is to cast to the first child class
            child_class = next(iter(self._child_classes.values()))
        else:
            # we use r here and not existing_instance because if
            # existing_instance gets overridden, it won't contain the line
            # we're trying to parse
            key_value = self.get_by_field(r, self._key)

            child_class = self._child_classes.get(key_value)
            if child_class is None:
                # FIXME: Unknown value, should log
                # print("Unknown value {1} class {0}".format(self.label(), key_value))
                self._unknown_values.setdefault(key_value, 0)
                self._unknown_values[key_value] += 1
                return r

        # Found the child class, move down in hierarchy
        return child_class.parse(existing_instance, text)

    def get_field(self, field_name):
        f = self._fields.get(field_name)
        if f is not None:
            return f
        # otherwise
        if self._parent is None:
            return None
        return self._parent.get_field(field_name)

    def get_field_multi(self, field_name):
        if isinstance(field_name, tuple):
            ret = [self.get_field(f) for f in field_name]
            if None in ret:
                return None
            else:
                return ret
        else:
            return self.get_field(field_name)

    def get_by_field(self, instance, field):
        if type(field) is list:
            vals = [self.get_by_field(instance, f) for f in field]
            return tuple(vals)
        else:
            return field.render(instance.text)

    def get(self, instance, field_name):
        f = self.get_field(field_name)
        if f is None:
            return None
        return self.get_by_field(instance, f)

    def name(self, instance):
        if self._name_field is None:
            return None
        return self.get_by_field(instance, self._name_field)

    def label(self):
        return self._label

    def get_type(self, typ: str):
        return next(c for c in self._child_classes.values() if c.label() == typ)

    def get_types(self):
        return self._child_classes

    def instances(self):
        return self._instances

    def get_fields(self):
        """
        List the fields applicable to an instance of this class, starting with the fields closer to the root of the hierarchy,
        and working down to this most-derived class
        """
        if self._required_auxiliary_record_cls is not None:
            aux_class = next(filter(lambda x: x.label() == self._required_auxiliary_record_cls, self._child_classes.values()))
            retval = aux_class._fields.values()
        else:
            retval = self._fields.values()

        return retval


base_record_class_fields = [
    Field("record_type", 0, 1),
    area_code_field,
    Field("section_code", 4, 5)
]
base_record_class = RecordClass("Record", None, None, "section_code", base_record_class_fields, None)

enroute_class_fields = [
    Field("subsection_code", 5, 6)
]
enroute_class = RecordClass("Enroute", base_record_class, "E", "subsection_code", enroute_class_fields, None)

enroute_waypoint_class_fields = [
    Field("waypoint_identifier", 13, 18),
    Field("icao_code", 19, 21),
    Field("continuation_record_no", 21, 22),
    Field("waypoint_type", 26, 29),
    Field("waypoint_usage", 29, 31),
    Field("latitude", 32, 41),
    Field("longitude", 41, 51),
    Field("magnetic_variation", 74, 79),
    Field("datum", 84, 87),
    Field("name_format_identifier", 95, 98),
    Field("waypoint_name", 98, 123)
]
enroute_waypoint_class = RecordClass("EnrouteWaypoint", enroute_class, "A", None, enroute_waypoint_class_fields, "waypoint_identifier")

enroute_airway_class_fields = [
    FieldSpacePadded("route_identifier", 13, 18),
    Field("sequence_number", 25, 29),
    FieldSpacePadded("fix_identifier", 29, 34),
    Field("icao_code", 34, 36),
    Field("section_code2", 36, 37),
    Field("subsection_code2", 37, 38),
    Field("continuation_record_no", 38, 39),
    Field("waypoint_description_code", 39, 43),
    Field("boundary_code", 43, 44),
    Field("route_type", 44, 45),
    Field("level", 45, 46),
    Field("direction_restriction", 46, 47),
    Field("cruise_table_indicator", 47, 49),
    Field("eu_indicator", 49, 50),
    Field("recommended_navaid", 50, 54),
    Field("icao_code", 54, 56),
    Field("rnp", 56, 59),
    Field("theta", 62, 66),
    Field("rho", 66, 70),
    Field("outbound_magnetic_course", 70, 74),
    Field("route_distance_from", 74, 78),
    Field("inbound_magnetic_course", 78, 82),
    Field("minimum_altitude", 83, 88),
    Field("minimum_altitude2", 88, 93),
    Field("maximum_altitude", 93, 98),
    Field("fix_radius_transition_indicator", 99, 101)
]
enroute_airway_class = RecordClass("EnrouteAirway", enroute_class, "R", None, enroute_airway_class_fields, "route_identifier")

airport_class_fields = [
    FieldSpacePadded("code", 6, 10),
    Field("subsection_code", 12, 13)
]
airport_class = RecordClass("Airport", base_record_class, "P", "subsection_code", airport_class_fields, "code", required_auxiliary_record_cls="AirportPrimaryRecord")

airport_primary_record_class_fields = [
    FieldSpacePadded("iata_designator", 13, 16),
    Field("continuation_record_number", 21, 22),
    Field("speed_limit_altitude", 22, 27),
    FieldZeroPadded("longest_runway", 27, 30),
    Field("ifr_capability", 30, 31),
    Field("longest_runway_surface_code", 31, 32),
    FieldLatLng("latitude", 32, 41),
    FieldLatLng("longitude", 41, 51),
    Field("magnetic_variation", 51, 56),
    FieldZeroPadded("airport_elevation", 56, 61),
    Field("speed_limit", 61, 64),
    Field("datum", 86, 89),
    FieldSpacePadded("name", 93, 123)
]
airport_primary_record_class = RecordClass("AirportPrimaryRecord", airport_class, "A", None, airport_primary_record_class_fields, None)

airport_runway_class_fields = [
    FieldSpacePadded("runway_identifier", 13, 18),
    Field("continuation_record_number", 21, 22),
    FieldZeroPadded("runway_length", 22, 27),
    Field("runway_magnetic_bearing", 27, 31),
    Field("latitude", 32, 41),
    Field("longitude", 41, 51),
    Field("runway_gradient", 51, 56),
    FieldZeroPadded("runway_threshold_elevation", 66, 71),
    FieldZeroPadded("displaced_threshold", 71, 75),
    Field("threshold_crossing_height", 75, 77),
    Field("runway_width", 77, 80),
    Field("approach_navaid", 81, 85),
    Field("navaid_class", 85, 86),
    Field("stopway", 86, 90),
    Field("second_navaid", 90, 94),
    Field("navaid_class", 94, 95),
    FieldSpacePadded("name", 101, 123)
]
airport_runway_class = RecordClass("AirportRunway", airport_class, "G", None, airport_runway_class_fields, ("code", "runway_identifier"))


airport_dep_arr_app_class_fields = [
    FieldSpacePadded("identifier", 13, 19)
]
airport_departure_class = RecordClass("AirportDeparture", airport_class, "D", None, airport_dep_arr_app_class_fields, ("code", "identifier"))
airport_arrival_class = RecordClass("AirportArrival", airport_class, "E", None, airport_dep_arr_app_class_fields, ("code", "identifier"))
airport_approach_class = RecordClass("AirportApproach", airport_class, "F", None, airport_dep_arr_app_class_fields, ("code", "identifier"))


airport_dep_arr_app_transition_class_fields = [
    Field("route_type", 19, 20),
    FieldSpacePadded("transition_identifier", 20, 25)
]
airport_approach_transition_class = RecordClass("AirportApproachTransition", airport_approach_class, None, None, airport_dep_arr_app_transition_class_fields, ("code", "identifier", "transition_identifier"))
airport_departure_transition_class = RecordClass("AirportDepartureTransition", airport_departure_class, None, None, airport_dep_arr_app_transition_class_fields, ("code", "identifier", "transition_identifier"))
airport_arrival_transition_class = RecordClass("AirportArrivalTransition", airport_arrival_class, None, None, airport_dep_arr_app_transition_class_fields, ("code", "identifier", "transition_identifier"))

airport_dep_arr_app_waypoint_class_fields = [
    Field("sequence_number", 26, 29),
    Field("fix_identifier", 29, 34),
    Field("icao_code", 34, 36),
    Field("section_code2", 36, 37),
    Field("subsection_code2", 37, 38),
    Field("continuation_record_no", 38, 39),
    Field("waypoint_description_code", 39, 43),
    Field("turn_direction", 43, 44),
    Field("rnp", 44, 47),
    Field("path_and_termination", 47, 49),
    Field("turn_direction_valid", 49, 50),
    Field("recommended_navaid", 50, 54),
    Field("icao_code2", 54, 56),
    Field("arc_radius", 56, 62),
    Field("theta", 62, 66),
    Field("rho", 66, 70),
    Field("magnetic_course", 70, 74),
    Field("distance_or_time", 74, 78),
    Field("recd_nav_section", 78, 79),
    Field("recd_nav_subsection", 79, 80),
    Field("altitude_description", 82, 83),
    Field("atc_indicator", 83, 84),
    Field("altitude", 84, 89),
    Field("altitude2", 89, 94),
    Field("transition_altitude", 94, 99),
    Field("speed_limit", 99, 102),
    Field("vertical_angle", 102, 106),
    Field("center_fix_or_taa_indic", 106, 111),
    Field("multiple_code", 111, 112),
    Field("icao_code", 112, 114),
    Field("section_code", 114, 115),
    Field("subsection_code", 115, 116),
    Field("gps_fms_indicator", 116, 117),
    Field("speed_limit_description", 117, 118),
    Field("apch_route_qualifier_1", 118, 119),
    Field("apch_route_qualifier_2", 119, 120),
]
airport_departure_waypoint_class = RecordClass("AirportDepartureWaypoint", airport_departure_transition_class, None, None, airport_dep_arr_app_waypoint_class_fields, ("code", "identifier", "transition_identifier", "fix_identifier"))
airport_arrival_waypoint_class = RecordClass("AirportArrivalWaypoint", airport_arrival_transition_class, None, None, airport_dep_arr_app_waypoint_class_fields, ("code", "identifier", "transition_identifier", "fix_identifier"))
airport_approach_waypoint_class = RecordClass("AirportApproachWaypoint", airport_approach_transition_class, None, None, airport_dep_arr_app_waypoint_class_fields, ("code", "identifier", "transition_identifier", "fix_identifier"))

airport_waypoint_class = RecordClass("AirportWaypoint", airport_class, "C", None, enroute_waypoint_class_fields, "waypoint_identifier")

airport_path_point_class_fields = [
    Field("identifier", 13, 19),
    Field("runway_or_helipad", 19, 24),
    Field("operation_type", 24, 26),
    Field("continuation_record_no", 26, 27),
    Field("route_indicator", 27, 28),
    Field("sbas_service_provider_identifier", 28, 30),
    Field("reference_path_data_selector", 30, 32),
    Field("reference_path_identifier", 32, 36),
    Field("approach_performance_designator", 36, 37),
    Field("landing_threshold_point_latitude", 37, 48),
    Field("landing_threshold_point_longitude", 48, 60),
    Field("ellipsoid_height", 60, 66),
    Field("glide_path_angle", 66, 70),
    Field("flight_path_alignment_latitude", 70, 81),
    Field("flight_path_alignment_longitude", 81, 93),
    Field("course_width_at_threshold", 93, 98),
    Field("length_offset", 98, 102),
    Field("path_point_tch", 102, 108),
    Field("tch_units_indicator", 108, 109),
    Field("hal", 109, 112),
    Field("val", 112, 115),
    Field("sbas_fas_crc_remainder", 115, 123),
    Field("file_record_no", 123, 128),
    Field("cycle_date", 128, 132),

]
airport_path_point_class = RecordClass("AirportPathPoint", airport_class, "P", None, airport_path_point_class_fields, ("code", "identifier"))

heliport_class_fields = [
    FieldSpacePadded("code", 6, 10),
    Field("subsection_code", 12, 13)
]
heliport_class = RecordClass("Heliport", base_record_class, "H", "subsection_code", heliport_class_fields, "code", required_auxiliary_record_cls="HeliportPrimaryRecord")

heliport_primary_record_class_fields = [
    FieldSpacePadded("iata_designator", 13, 16),
    Field("pad_identifier", 16, 21),
    Field("continuation_record_number", 21, 22),
    Field("speed_limit_altitude", 22, 27),
    Field("datum", 27, 30),
    Field("ifr_capability", 30, 31),
    FieldLatLng("latitude", 32, 41),
    FieldLatLng("longitude", 41, 51),
    Field("magnetic_variation", 51, 56),
    FieldZeroPadded("heliport_elevation", 56, 61),
    Field("speed_limit", 61, 64),
    Field("recommended_vhf_navaid", 64, 68),
    Field("transition_altitude", 70, 75),
    Field("transition_level", 75, 80),
    Field("public_military_indicator", 80, 81),
    Field("time_zone", 81, 84),
    Field("daylight_indicator", 84, 85),
    Field("pad_dimensions", 85, 91),
    Field("magnetic_true_indicator", 91, 92),
    FieldSpacePadded("name", 93, 123)
]
heliport_primary_record_class = RecordClass("HeliportPrimaryRecord", heliport_class, "A", None, heliport_primary_record_class_fields, None)

heliport_dep_arr_app_class_fields = [
    FieldSpacePadded("identifier", 13, 19)
]
heliport_departure_class = RecordClass("HeliportDeparture", heliport_class, "D", None, heliport_dep_arr_app_class_fields, ("code", "identifier"))
heliport_arrival_class = RecordClass("HeliportArrival", heliport_class, "E", None, heliport_dep_arr_app_class_fields, ("code", "identifier"))
heliport_approach_class = RecordClass("HeliportApproach", heliport_class, "F", None, heliport_dep_arr_app_class_fields, ("code", "identifier"))

heliport_dep_arr_app_transition_class_fields = [
    Field("route_type", 19, 20),
    FieldSpacePadded("transition_identifier", 20, 25)
]
heliport_approach_transition_class = RecordClass("HeliportApproachTransition", heliport_approach_class, None, None, heliport_dep_arr_app_transition_class_fields, ("code", "identifier", "transition_identifier"))
heliport_departure_transition_class = RecordClass("HeliportDepartureTransition", heliport_departure_class, None, None, heliport_dep_arr_app_transition_class_fields, ("code", "identifier", "transition_identifier"))
heliport_arrival_transition_class = RecordClass("HeliportArrivalTransition", heliport_arrival_class, None, None, heliport_dep_arr_app_transition_class_fields, ("code", "identifier", "transition_identifier"))

heliport_departure_waypoint_class = RecordClass("HeliportDepartureWaypoint", heliport_departure_transition_class, None, None, airport_dep_arr_app_waypoint_class_fields, ("code", "identifier", "transition_identifier", "fix_identifier"))
heliport_arrival_waypoint_class = RecordClass("HeliportArrivalWaypoint", heliport_arrival_transition_class, None, None, airport_dep_arr_app_waypoint_class_fields, ("code", "identifier", "transition_identifier", "fix_identifier"))
heliport_approach_waypoint_class = RecordClass("HeliportApproachWaypoint", heliport_approach_transition_class, None, None, airport_dep_arr_app_waypoint_class_fields, ("code", "identifier", "transition_identifier", "fix_identifier"))


navaid_class_fields = [
    Field("subsection_code", 5, 6),
]
navaid_class = RecordClass("Navaid", base_record_class, "D", "subsection_code", navaid_class_fields, None)


vhf_navaid_class_fields = [
    FieldSpacePadded("airport_code", 6, 10),
    FieldSpacePadded("vor_identifier", 13, 17),
    Field("icao_code", 19, 21),
    Field("continuation_record_no", 21, 22),
    Field("vor_frequency", 22, 27),
    Field("navaid_class", 27, 32),
    FieldLatLng("latitude", 32, 41),
    FieldLatLng("longitude", 41, 51),
    Field("dme_ident", 51, 55),
    Field("dme_latitude", 55, 64),
    Field("dme_longitude", 64, 74),
    Field("station_declination", 74, 79),
    Field("dme_elevation", 79, 84),
    Field("figure_of_merit", 84, 85),
    Field("ils_dme_bias", 85, 87),
    Field("frequency_protection", 87, 90),
    Field("datum", 90, 93),
    FieldSpacePadded("name", 93, 123)
]
vhf_navaid_class = RecordClass("VHFNavaid", navaid_class, " ", None, vhf_navaid_class_fields, ("area_code", "vor_identifier"))

ndb_navaid_class_fields = [
    FieldSpacePadded("airport_code", 6, 10),
    FieldSpacePadded("icao_code", 10, 12),
    Field("ndb_identifier", 13, 17),
    Field("icao_code", 19, 21),
    Field("continuation_record_no", 21, 22),
    Field("ndb_frequency", 22, 27),
    Field("ndb_class", 27, 32),
    Field("latitude", 32, 41),
    Field("longitude", 41, 51),
    Field("station_declination", 74, 79),
    Field("datum", 90, 93),
    FieldSpacePadded("name", 93, 123)
]
ndb_navaid_class = RecordClass("NDBNavaid", navaid_class, "B", None, ndb_navaid_class_fields, "ndb_identifier")


airspace_class_fields = [
    Field("subsection_code", 5, 6),
]
airspace_class = RecordClass("Airspace", base_record_class, "U", "subsection_code", airspace_class_fields, None)

controlled_airspace_class_fields = [
    FieldSpacePadded("icao_code", 6, 8),
    Field("airspace_type", 8, 9),
    FieldSpacePadded("airspace_center", 9, 14),
    Field("section_code2", 14, 15),
    Field("subsection_code2", 15, 16),
    Field("airspace_classification", 16, 17),
    Field("multiple_code", 19, 20),
    Field("sequence_number", 20, 24),
    Field("continuation_record_no", 24, 25),
    Field("level", 25, 26),
    Field("time_code", 26, 27),
    Field("notam", 27, 28),
    FieldSpacePadded("boundary_via", 30, 32),
    Field("latitude", 32, 41),
    Field("longitude", 41, 51),
    Field("arc_origin_latitude", 51, 60),
    Field("arc_origin_longitude", 60, 70),
    Field("arc_distance", 70, 74),
    Field("arc_bearing", 74, 78),
    Field("rnp", 78, 81),
    Field("lower_limit", 81, 86),
    Field("unit_indicator", 86, 87),
    Field("upper_limit", 87, 92),
    Field("unit_indicator2", 92, 93),
    FieldSpacePadded("name", 93, 123)
]
controlled_airspace_class = RecordClass("ControlledAirspace", airspace_class, "C", None, controlled_airspace_class_fields, ("airspace_center", "airspace_classification", "multiple_code"))


restrictive_airspace_class_fields = [
    FieldSpacePadded("icao_code", 6, 8),
    Field("restrictive_type", 8, 9),
    FieldSpacePadded("airspace_designation", 9, 19),
    Field("multiple_code", 19, 20),
    Field("sequence_number", 20, 24),
    Field("continuation_record_no", 24, 25),
    Field("level", 25, 26),
    Field("time_code", 26, 27),
    Field("notam", 27, 28),
    FieldSpacePadded("boundary_via", 30, 32),
    Field("latitude", 32, 41),
    Field("longitude", 41, 51),
    Field("arc_origin_latitude", 51, 60),
    Field("arc_origin_longitude", 60, 70),
    Field("arc_distance", 70, 74),
    Field("arc_bearing", 74, 78),
    Field("lower_limit", 81, 86),
    Field("unit_indicator", 86, 87),
    Field("upper_limit", 87, 92),
    Field("unit_indicator2", 92, 93),
    FieldSpacePadded("name", 93, 123)
]
restrictive_airspace_class = RecordClass("RestrictiveAirspace", airspace_class, "R", None, restrictive_airspace_class_fields, ("restrictive_type", "airspace_designation", "multiple_code"))


class ArincFile:
    def __init__(self, fname: str) -> None:
        with open(fname, "rb") as f:
            # Skip some special records
            next(f)
            next(f)
            next(f)
            next(f)
            next(f)

            for line in f:
                line = line[0:-1].decode("ascii")

                self.add_record(line)

    def add_record(self, text: str) -> None:
        try:
            base_record_class.parse(None, text)
        except:
            print("Error was with line:")
            print(text)
            raise

    def get_types(self):
        return base_record_class._child_classes

    def get_type(self, typ: str):
        return base_record_class.get_type(typ)

    def get_unknowns(self, starting_class=None, path=""):
        """
        This prints all the unknown fields are how many were found
        """
        if starting_class is None:
            starting_class = base_record_class

        has_unknown_records = False
        has_unknown_continuations = False
        if len(starting_class._unknown_values):
            has_unknown_records = True
        if len(starting_class._unused_continuations):
            has_unknown_continuations = True

        if has_unknown_records or has_unknown_continuations:
            print(f"For class {starting_class.label()}")

        if has_unknown_records:
            print("\tHere are the unknown record types:")
            for typ, count in starting_class._unknown_values.items():
                print(f"\t\t{typ} ({count} records)")

        if has_unknown_continuations:
            print("\tHere are the unknown continuation records:")
            for cont_no, count in starting_class._unused_continuations.items():
                print(f"\t\t{cont_no} ({count} records)")

        for child_class in starting_class.get_types().values():
            self.get_unknowns(child_class, f"{path} / {starting_class.label()}")
