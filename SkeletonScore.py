#!/usr/bin/python2.7

# This is pretty much a direct translation of Hello.java into Python.
import sys
import os

import json

def srange(x):
    return 0.1*x+0.9

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

TRIPS_NAME="SkeletonScore"
TRIPS_BASE = os.environ['TRIPS_BASE']
tmpfilename = os.path.join(TRIPS_BASE, "etc/Data/tmp")

load_tmp_file = lambda fname: [x for x in json.load(open(fname)) if 'lftype' in x or 'senses' in x]

SUBSCRIPTIONS = [
        "wsd-check",
        "get-wsd-data",
        "paragraph-completed",
        "new-speech-act-hyps"
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
        TripsModule.__init__(self, argv)

    def init(self):
        self.name = TRIPS_NAME
        TripsModule.init(self)
        self.subscribe_to_verb(TRIPS_NAME)
        for verb in SUBSCRIPTIONS:
            self.subscribe_to_verb(verb)
        self.ready()

    def receive_tell(self, msg, content):
        verb = content[0].to_string().lower()
        if verb in ["paragraph-completed", "new-speach-act-hyps"]:
            if os.path.isfile(tmpfilename):
                os.remove(tmpfilename)

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

        if verb == "get-wsd-data":
            print("get-wsd-data")
            if os.path.isfile(tmpfilename):
                res = load_tmp_file(tmpfilename)
            else:
                res = []
            # Currently, expecting something like
            # {"lftype": "ont::something", "lex": "w::something", "start": 1, "end": 2, "score": 1}
            data = KQMLList()
            data.add("add-wsd-data")

            for r in res:
                if 'senses' in r:
                    r["senses"] = dict(r.get("senses", {}))
                    for sense, score in r["senses"].items():
                        d = KQMLList()
                        span = KQMLList()
                        d.add(sense)
                        d.add("w::"+r['lex'])
                        span.add(int(r['start']))
                        span.add(int(r['end']))
                        d.add(span)
                        d.add(":WSD")
                        d.add(srange(score))
                        data.add(d)
                elif 'lftype' in r and r['lftype']:
                    lftype = r['lftype'][0]
                    d = KQMLList()
                    span = KQMLList()
                    d.add(lftype)
                    d.add("w::"+r['lex'])
                    span.add(int(r['start']))
                    span.add(int(r['end']))
                    d.add(span)
                    d.add(":WSD")
                    d.add(float(r.get("score", 1)))
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

