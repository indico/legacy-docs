import getopt, sys
from MaKaC.common import DBMgr
from MaKaC.conference import ConferenceHolder
from MaKaC.common.url import ShortURLMapper
 
def usage():
    print "Usage: %s -i 44 -t tag" % sys.argv[0]

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "i:t:", ["id=","tag="])
    except getopt.GetoptError, err:
        # print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        usage()
        sys.exit(0)
    id = None
    tag = None 
    for o, a in opts:
        if o == "-i":
            id = str(a)
        elif o == "-t":
            tag = str(a)
        else:
            assert False, "unhandled option"
 
    dbi = DBMgr.getInstance()
    dbi.startRequest()

    if id and tag:
        ch = ConferenceHolder()
        conf = ch.getById(id)
        print "Setting ShortURLTag of %s to %s" % (conf.getTitle(), tag)
        sum = ShortURLMapper()
        sum.add(tag,conf)
    else:
        usage()
        sys.exit(0)
    dbi.endRequest()
    dbi.commit()
if __name__ == "__main__":
    main()
