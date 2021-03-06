#!/usr/bin/python2.7

# This is pretty much a direct translation of Hello.java into Python.
import sys
import os

import json

# this should load bioagents if the trips version is less than 3
# and tripsmodule otherwise
if sys.version_info < (3, 0):
    print("loading bioagents")
    from bioagents_trips.trips_module import TripsModule
    from bioagents_trips.kqml_performative import KQMLPerformative
    from bioagents_trips.kqml_list import KQMLList
    def decode_me(s):
        return s.decode("string_escape").replace(",}", "}")
else:
    print("load tripsmodule instead")
    from tripsmodule.trips_module import TripsModule
    from tripsmodule.kqml_performative import KQMLPerformative
    from tripsmodule.kqml_list import KQMLList
    import codecs
    def decode_me(s):
        return codecs.escape_decode(s)[0].decode("utf-8").replace("\"\"{", "{").replace("}\"\"", "}").replace(",}", "}").replace("\\\"", "\"")

import diesel.ontology as ontology
import diesel.library as library
import diesel.score as score

TRIPS_NAME="SkeletonScore"
TRIPS_BASE = os.environ['TRIPS_BASE']
ONTOLOGY_PATH = os.path.join(TRIPS_BASE, "etc/XMLTrips/lexicon/data")
GOLD_DATA = os.path.join(TRIPS_BASE, "etc/Data/gold.predmap")
ALTERNATE_DATA = os.path.join(TRIPS_BASE, "etc/Data/test.predmap")

if os.path.isfile(ALTERNATE_DATA):
    GOLD_DATA = ALTERNATE_DATA

LIBRARY = library.DEFAULT_LIBRARY


class SkeletonScore(TripsModule):
    """ Hello TRIPS module - replies to hello requests with hello tells.
    Sending this: (request :content (hello) :sender fred)
    Gets this reply: (tell :content (hello fred) :receiver fred)
    """
    def subscribe_to_verb(self, verb):
        self.send(KQMLPerformative.from_string(
            "(subscribe :content (request &key :content ({} . *)))".format(verb)))

    def __init__(self, argv):
        self.name = TRIPS_NAME
        self.ontology = ontology.load_ontology(ONTOLOGY_PATH)
        self.gold = library.load_predmap(GOLD_DATA, self.ontology, lib_type=LIBRARY)
        self.PRED_TYPE = score.DEFAULT_PRED_TYPE

        TripsModule.__init__(self, argv)

    def init(self):
        self.name = TRIPS_NAME
        self.ontology = ontology.load_ontology(ONTOLOGY_PATH)
        self.gold = library.load_predmap(GOLD_DATA, self.ontology, lib_type=LIBRARY)
        self.PRED_TYPE = score.DEFAULT_PRED_TYPE
        TripsModule.init(self)
        self.subscribe_to_verb(TRIPS_NAME)
        self.subscribe_to_verb("adjustment-factor")
        self.subscribe_to_verb("adjustment-factor2")
        self.subscribe_to_verb("score-method")
        self.subscribe_to_verb("selection-method")
        self.subscribe_to_verb("evaluate-skeleton")
        self.subscribe_to_verb("wsd-check")
        self.subscribe_to_verb("use-skeleton-data")
        self.ready()

    def receive_request(self, msg, content):
        #print('rec:', msg, content)
        error = False
        if not isinstance(content, KQMLList):
            self.error_reply(msg, "expected :content to be a list")
            return
        verb = content[0].to_string().lower()
        reply_msg = KQMLPerformative("tell")
        reply_content = KQMLList()
        print("rec:", verb)

        if verb == "use-skeleton-data":
            global GOLD_DATA
            reply_content.add("use-skeleton-data")
            reply_content.add("ok")
            GOLD_DATA = content[1].to_string().lower().encode('ascii', 'ignore')
            self.gold = library.load_flatfile(GOLD_DATA, self.ontology, lib_type=LIBRARY)

        elif verb == "selection-method":
            global LIBRARY
            if content[1].to_string().isdigit():
                lib_index = int(content[1].to_string())
                if -1 < lib_index < len(library.LIBRARIES):
                    LIBRARY = library.LIBRARIES[lib_index]
                    reply_content.add("selection-method")
                    reply_content.add(LIBRARY.name())
                else:
                    error = True
                    self.error_reply(msg, "index out of range")
            else:
                lib_name = content[1].to_string()
                candidates = filter(lambda x: x.name() == lib_name, library.LIBRARIES)
                if len(candidates) == 1:
                    LIBRARY = candidates[0]
                    reply_content.add("selection-method")
                    reply_content.add(LIBRARY.name())
                else:
                    error = True
                    self.error_reply(msg, "found {} matching candidates. did not continue".format(len(candidates)))

        elif verb == "adjustment-factor":
            reply_content.add("adjustment-factor")
            reply_content.add("ok")
            adj_factor = content[1].to_string().lower().encode('ascii', 'ignore')
            self.gold.adjustment_factor = adj_factor

        elif verb == "score-method":
            if content[1].to_string().isdigit():
                pred_index = int(content[1].to_string())
                if -1 < pred_index < len(score.PREDICATES):
                    self.PRED_TYPE = score.PREDICATES[pred_index]
                    reply_content.add("score-method")
                    reply_content.add(self.PRED_TYPE.name())
                else:
                    error = True
                    self.error_reply(msg, "index out of range")
            else:
                pred_name = content[1].to_string()
                candidates = filter(lambda x: x.name() == pred_name, score.PREDICATES)
                if len(candidates) == 1:
                    self.PRED_TYPE = candidates[0]
                    reply_content.add("score-method")
                    reply_content.add(self.PRED_TYPE.name())
                else:
                    error = True
                    self.error_reply(msg, "found {} matching candidates. did not continue".format(len(candidates)))

        elif verb == "evaluate-skeleton":
            #predicate = content[1].to_string().encode("ascii", "ignore").lower()
            predicate = content[1].to_string().lower()
            print(predicate, file=sys.stderr)
            result = self.gold.adjustment_factor(predicate, True, pred_type=self.PRED_TYPE)
            str_res = ":score ({}) :match ({}) :to ({})".format(result[1], str(result[0]), predicate)

            # Broadcast predicate scores to all other agents just in case
            broadcast_msg = KQMLPerformative("tell")
            broadcast_content = KQMLList()
            broadcast_content.add("skelscore {}".format(str_res))
            broadcast_msg.set_parameter(":content", broadcast_content)
            self.send(broadcast_msg)

            reply_content.add(str_res)

        elif verb == "wsd-check":
            print(content)
            root = decode_me(content.get_keyword_arg(":ROOT").to_string().lower()[1:-1])
            print("|"+root+"|")
            roles = decode_me(content.get_keyword_arg(":ROLES").to_string().lower()[1:-1])
            print(json.loads(root))
            print(roles)
            print(type(json.loads(roles)))
            print({x : type(y) for x, y in json.loads(roles).items()})
            str_res = ":score ({}) :match ({}) :to ({})".format(str(1.0), "NONE", "NONE")
            broadcast_msg = KQMLPerformative("tell")
            broadcast_content = KQMLList()
            broadcast_content.add("skelscore {}".format(str_res))
            broadcast_msg.set_parameter(":content", broadcast_content)
            self.send(broadcast_msg)

            reply_content.add(str_res)

        #else:
        #    error = True
        #    reply_content.add("unknown")
        if not error:
            sender = msg.get_parameter(":sender")
            if sender is not None:
                reply_content.add(sender)
            reply_msg.set_parameter(":content", reply_content)
            self.reply(msg, reply_msg)


if __name__ == "__main__":
    import sys
    SkeletonScore(sys.argv[1:]).start()

