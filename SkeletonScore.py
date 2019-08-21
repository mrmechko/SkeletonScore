#!/usr/bin/python2.7

# This is pretty much a direct translation of Hello.java into Python.
import sys
import os

import json

def point_intersect(p, s):
    return s[0] <= p and p <= s[1]

def span_intersect(s1, s2):
    if s1[1] < s2[1]:
        return span_intersect(s2, s1)
    a, b = s2
    return point_intersect(a, s1) or point_intersect(b, s2)

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
tmpfilename = os.path.join(TRIPS_BASE, "etc/Data/tmp")
ALTERNATE_DATA = os.path.join(TRIPS_BASE, "etc/Data/test.predmap")

if os.path.isfile(ALTERNATE_DATA):
    GOLD_DATA = ALTERNATE_DATA

LIBRARY = library.DEFAULT_LIBRARY

load_tmp_file = lambda fname: [x for x in json.load(open(fname)) if x['lftype']]


SUBSCRIPTIONS = [
        "adjustment-factor",
        "adjustment-factor2",
        "score-method",
        "selection-method",
        "evaluate-skeleton",
        "wsd-check",
        "get-wsd-data",
        "use-skeleton-data"
        ]

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
        for verb in SUBSCRIPTIONS:
            self.subscribe_to_verb(verb)
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

        elif verb == "get-wsd-data":
            print("get-wsd-data")
            res = load_tmp_file(tmpfilename)
            # word, class, start, end
            # word =  content.get_keyword_arg(":WORD").to_string().lower()
            # cls =  content.get_keyword_arg(":CLASS").to_string().lower()
            # start =  content.get_keyword_arg(":START").to_string()
            # end =  content.get_keyword_arg(":END").to_string()
            data = KQMLList()
            data.add("add-wsd-data")

            for r in res:
                if not r['lftype']:
                    continue
                lftype = r['lftype'][0]
                d = KQMLList()
                span = KQMLList()
                d.add(lftype)
                d.add("w::"+r['lex'])
                span.add(int(r['start']))
                span.add(int(r['end']))
                d.add(span)
                data.add(d)
            broadcast_msg = KQMLPerformative("tell")
            broadcast_msg.set_parameter(":content", data)
            #this is duplicating things
            #self.send(broadcast_msg)
            print(broadcast_msg.to_string())
            reply_content = data

        elif verb == "wsd-check":
            res = load_tmp_file(tmpfilename)
            root = json.loads(decode_me(content.get_keyword_arg(":ROOT").to_string().lower()[1:-1]))
            roles = json.loads(decode_me(content.get_keyword_arg(":ROLES").to_string().lower()[1:-1]))
            #roles = {x : json.loads(y) for x, y in json.loads(roles).items()}
            all_nodes = list(roles.values()) + [root]
            score = 0
            out_of = 0
            print("++++")
            for y in all_nodes:
                print(y['class'], (y['start'], y['end']))

            print("----")

            for x in res:
                if not x['lftype']:
                    continue
                print(x['lftype'][0].lower(), (x['start'], x['end']))

            print("----")

            for y in all_nodes:
                if not y["class"].lower().startswith("ont::"):
                    continue
                out_of += 1
                for x in res:
                    if span_intersect((x['start'], x['end']), (int(y['start']), int(y['end']))):
                        if x['lftype'][0].lower() == y["class"].lower():
                            score += 1
            if score == out_of: #div by 0 guard
                score = 1
                out_of = 1
            score_res = (score/out_of)*0.1 + 0.95
            str_res = ":score ({}) :match ({}) :to ({})".format(str(score_res), "NONE", "NONE")
            print(str_res)
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
            # why is the sender being appended to the message?
            #sender = msg.get_parameter(":sender")
            #if sender is not None:
            #    reply_content.add(sender)
            reply_msg.set_parameter(":content", reply_content)
            self.reply(msg, reply_msg)


if __name__ == "__main__":
    import sys
    SkeletonScore(sys.argv[1:]).start()

