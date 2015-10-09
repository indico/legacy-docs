import hashlib
import os
import re
import stat
import sys

MATCH_PYTHON_BLOCK = re.compile('<%.*?%>', re.DOTALL)
MATCH_FORMAT = re.compile('%\(([^)]+)\)s')
MATCH_DECLARE_NEW = re.compile('<%\s*declareTemplate\(newTemplateStyle\s*=\s*True\)\s*%>\n*')

def sha1(data):
    h = hashlib.sha1()
    h.update(data)
    return h.hexdigest()

def fix_template(path):
    print "Fixing %s..." % path,
    f = open(path, 'rb')
    template = '\n'.join(line.rstrip() for line in f)
    f.close()

    stored_blocks = {}
    def replace_blocks(m):
        block = m.group(0)
        block_hash = sha1(block)
        stored_blocks[block_hash] = block
        return '{{{%s}}}' % block_hash

    num_converted = [0] # list so we can modify it from inside the callback
    def convert_variables(m):
        name = m.group(1)
        num_converted[0] += 1
        return '<%%= %s %%>' % name

    fixed = MATCH_DECLARE_NEW.sub('', template)
    fixed = MATCH_PYTHON_BLOCK.sub(replace_blocks, fixed)
    fixed = MATCH_FORMAT.sub(convert_variables, fixed)
    if num_converted[0]:
        fixed = fixed.replace('%%', '%')
    for key, block in stored_blocks.iteritems():
        fixed = fixed.replace('{{{%s}}}' % key, block)

    if fixed == template:
        print ' nothing to do'
    else:
        print ' done [%d]' % num_converted[0]
        f = open(path, 'wb')
        f.write(fixed)
        f.close()


def walktree(top='.'):
    names = os.listdir(top)
    yield top, names
    for name in names:
        try:
            st = os.lstat(os.path.join(top, name))
        except os.error:
            continue
        if stat.S_ISDIR(st.st_mode):
            for newtop, children in walktree(os.path.join(top, name)):
                yield newtop, children

for basepath, children in walktree('cds-indico'):
    for child in children:
        if child.endswith('.tpl'):
            fix_template(os.path.join(basepath, child))
