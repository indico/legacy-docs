from MaKaC.common import DBMgr
from MaKaC.webinterface.session.sessionManagement import getSessionManager

def deleteSessions(sm,todelete):
    done = 0
    for key in todelete :
      sm.delete_session(key)
      done+=1
    try:
      DBMgr.getInstance().commit()
    except:
      DBMgr.getInstance().sync()
    print "deleted %s sessions" % (len(todelete))

DBMgr.getInstance().startRequest()
websessionDelay = float(24 * 3600)
sm = getSessionManager()
print "ok got session manager"
keys = sm.keys()
print "ok got keys"
done = 0
fresh = 0
todelete = []
batchsize = 1000

print "start deleting"
for key in keys:
  value = sm[key]
  try:
    if value.get_access_age() > websessionDelay:
      todelete.append(key)
    else:
      fresh+=1
      if (fresh%batchsize)==0:
        print "too fresh %s sessions" % (fresh)
  except:
    print "cannot delete %s" % key
  if len(todelete) >= batchsize :
    deleteSessions(sm,todelete)
    todelete = []

if len(todelete) > 0 :
    deleteSessions(sm,todelete)

print "too fresh %s sessions" % (fresh)

DBMgr.getInstance().endRequest()
